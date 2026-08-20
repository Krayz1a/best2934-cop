"""Fire the counted report at settlement, with no human in the loop (rule 32).

Rule 32 makes reporting the agent's job, not the operator's. Our reporting
service has said so in its own docstring since it was written -- *"the agent --
not a human -- e-mails the result to the lecturer. That is what makes it an
agent rather than a script someone runs"* -- and it was not true. The only
caller of :meth:`ReportingService.send_result` was the ``send-report`` CLI
command, which a person runs by hand with ``--live``. Every flight this week
was operator-armed.

imreeyal named it as the one item they needed in writing before a counted
series: an operator-armed send is a single point of failure, and rule 35 prices
a missing report at *both* teams' scores. They were right, and the honest fix
was to build the thing rather than promise it.

Three guards, because an automatic mailer is also the most dangerous object in
this codebase:

*Counted only.* A friendly never mails the lecturer. The flag comes from the
pairing, not from an argument a caller can forget.

*Complete only.* :meth:`ReportingService.incompleteness` checks the played
sub-games against the **signed** ``num_sub_games``. imreeyal lost a series to a
consistent, incomplete report; consistent-and-short is the shape no self-check
inside the artifact can catch.

*Once.* ``refresh_result`` runs after **every** sub-game, so without a sentinel
the last one would fire on every subsequent re-run. The receipt on disk is the
sentinel, and it is written whether or not the send succeeded -- a failed send
must not silently retry into a rate limit, it must be visible and dealt with.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..reports.history import record_counted_game
from ..reports.naming import write_json
from ..shared.peer_config import PeerConfig
from .reporting_service import DeliveryReceipt, ReportingService

LOGGER = logging.getLogger(__name__)

#: Written beside the result the moment a counted report is attempted.
RECEIPT_PREFIX = "reported_"


def receipt_path(directory: Path, game_id: str) -> Path:
    return Path(directory) / f"{RECEIPT_PREFIX}{game_id}.json"


def already_fired(directory: Path, game_id: str) -> bool:
    return receipt_path(directory, game_id).exists()


def fire_if_settled(config: PeerConfig, opponent: str, result_path: Path,
                    counted: bool) -> DeliveryReceipt | None:
    """Mail the counted report if this sub-game completed the series.

    Returns the receipt when a send was attempted, and ``None`` when there was
    nothing to do -- a friendly, an unfinished series, or a report already
    filed. Never raises: a failure here must not take down the match that
    produced the result, because the artifacts on disk are still the evidence
    and an operator can still send by hand.
    """
    if not counted:
        return None

    directory = Path(result_path).parent
    if already_fired(directory, str(result_path.stem).replace("result_", "")):
        return None

    try:
        result = json.loads(Path(result_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        LOGGER.error("counted report NOT sent -- unreadable result: %s", error)
        return None

    game_id = str(result.get("game_id", ""))
    if already_fired(directory, game_id):
        return None

    service = ReportingService(config)
    short = service.incompleteness(result)
    if short:
        LOGGER.info("counted report held: %s", short)
        return None

    # Rule 37's ledger, written BEFORE the send and regardless of it. The
    # series happened; whether the mail leaves is a separate fact, and a
    # counted game that failed to post is still a counted game we must declare.
    #
    # Nothing wrote this ledger until now. `record_counted_game` existed, was
    # tested, and had no production caller -- so `counted_games_played` would
    # have answered 0 forever, however many counted series we played, and our
    # step-0 declaration to every future opponent would have been false under
    # rules 37-38. anrbj666 found it on league issue #49 by reading the output
    # of a check we posted to prove something else.
    #
    # No directory: the team-level ledger lives in `config/`, which is
    # role-independent, committed and synced between the two repositories.
    # Passing `artifacts_dir()` here wrote the PER-REPOSITORY ledger instead --
    # the same wrong-directory bug already fixed in `standings_block`, left
    # behind at this call site. It split the record in half: after the
    # anrbj666 counted series on 2026-08-20 the config ledger read
    # ["imreeyal", "gal-roy1"] and the artifacts one read
    # ["imreeyal", "anrbj666"], so neither file knew we had played three.
    # A count we under-report is a false declaration under rule 38 exactly as
    # much as one we inflate.
    record_counted_game(opponent)

    LOGGER.warning("SERIES SETTLED -- firing the counted report to %s (rule 32)",
                   config.email["recipient"])
    receipt = service.send_result(result)
    _record(directory, game_id, receipt, opponent)
    if not receipt.sent:
        LOGGER.error("COUNTED REPORT FAILED: %s -- send by hand, rule 35 voids "
                     "the match for BOTH teams on a missing report", receipt.reason)
    return receipt


def _record(directory: Path, game_id: str, receipt: DeliveryReceipt,
            opponent: str) -> Path:
    """Write the sentinel, so settlement is attempted exactly once.

    Written on failure too. A mailer that retries by itself every time the
    result is refreshed is how an account gets suspended mid-deadline, and a
    failure that is loud on disk is worth more than one that is quietly
    retried.
    """
    payload: dict[str, Any] = {
        "_schema": "Receipt for the automatic counted-series report (rule 32). "
                   "Its presence prevents a second send.",
        "game_id": game_id,
        "opponent": opponent,
        **receipt.as_dict(),
    }
    return write_json(receipt_path(directory, game_id), payload)
