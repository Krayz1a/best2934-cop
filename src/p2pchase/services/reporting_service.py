"""Autonomous result reporting, behind the Gatekeeper (book ch9.3, rules 33-35).

At the end of a match the agent -- not a human -- e-mails the result to the
lecturer. That is what makes it an agent rather than a script someone runs, and
it is also the single most dangerous thing this codebase does: a bug in the
match loop becomes a bug that sends mail in a loop, and Google's answer to that
is to suspend the account.

So every send goes through :class:`~p2pchase.infra.gatekeeper.ApiGatekeeper`.
There is no second path. :meth:`ReportingService.send_result` composes and
delegates; it never calls the API itself.

Rule 35 gives this service its other job: both teams must send, and the two
reports must agree. A dry run is therefore a first-class mode -- the report can
be built, digested and compared with the opponent before anyone sends anything.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..infra import gmail_sender
from ..infra.gatekeeper import ApiGatekeeper, build_gatekeeper
from ..reports.naming import opponent_in_game_id
from ..shared.peer_config import PeerConfig
from . import friendly_recipient

LOGGER = logging.getLogger(__name__)


@dataclass
class DeliveryReceipt:
    """What happened to one report."""

    sent: bool
    recipient: str
    subject: str
    attachment: str
    message_id: str = ""
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "sent": self.sent,
            "recipient": self.recipient,
            "subject": self.subject,
            "attachment": self.attachment,
            "message_id": self.message_id,
            "reason": self.reason,
        }


class ReportingService:
    """Composes the result e-mail and sends it through the Gatekeeper.

    Input:  a result artifact (the dict written to ``result_<game_id>.json``).
    Output: a :class:`DeliveryReceipt`.
    Setup:  a :class:`PeerConfig`; an optional pre-built Gatekeeper, which tests
            inject so no real quota is ever consumed.
    """

    def __init__(self, config: PeerConfig, gatekeeper: ApiGatekeeper | None = None) -> None:
        self.config = config
        self.gatekeeper = gatekeeper or build_gatekeeper(config.rate_limits, "gmail")

    # ------------------------------------------------------------- composing
    def subject(self, result: dict[str, Any], recipient: str = "") -> str:
        """Subject line, in the form the *reader* of this mail expects.

        Two readers, two conventions, and the difference is not cosmetic.

        The course address is `rmisegal+uoh26finalgame@gmail.com` -- a plus-tag,
        which exists to be filtered on. `[UOH26 Final Game]` was built to match
        it and stays for anything addressed there.

        An **opponent** sorts by the league's convention instead, and imreeyal
        settled which one that is from the book rather than from preference: no
        subject is mandated anywhere, the sole occurrence being the illustrative
        `send_report(...)` listing in Appendix A, which the book's own binding
        model calls illustrative. So it is convention, and the convention with
        precedent -- five counted series filed under it, plus najamjad's written
        adoption -- is the reference form. One series should file under one
        subject shape from both teams, and a counted settlement is the wrong
        place to discover that it did not.
        """
        if recipient and recipient != self.config.email["recipient"]:
            winner = result.get("final_result", {}).get("winner_group") or "tie"
            return (f"Police-Thief series result: winner {winner} "
                    f"(reported by {self.config.role})")
        return (
            f"[UOH26 Final Game] {result.get('game_id', 'unknown')} — "
            f"{self.config.group_id} result report"
        )

    def compose(self, result: dict[str, Any],
                recipient: str = "") -> tuple[dict[str, str], str]:
        """Build the raw message and the attachment filename."""
        attachment_name = f"result_{result.get('game_id', 'game')}.json"
        destination = recipient or self.config.email["recipient"]
        raw = gmail_sender.build_message(
            subject=self.subject(result, destination),
            attachment_name=attachment_name,
            attachment=result,
            sender=gmail_sender.sender_address(),
            recipient=destination,
        )
        return raw, attachment_name

    # ---------------------------------------------------------------- sending
    def incompleteness(self, result: dict[str, Any]) -> str:
        """Why this report must not be sent, or ``""`` when it is complete.

        imreeyal lost a series to exactly this and told us so: their driver
        stopped correctly at sub-game 3, then built and mailed a perfectly
        consistent two-game "series tie" for a six-game match. *Consistent and
        incomplete* is the dangerous shape -- nothing inside the artifact
        contradicts itself, so no self-check inside it can catch the fault, and
        rule 35 charges both teams when the two reports disagree.

        Their advice, adopted verbatim: the completeness check has to be an
        explicit assertion rather than a property of the loop's shape. Ours was
        the latter -- ``run_series`` iterates ``range(1, count + 1)`` and is
        therefore complete by construction, which holds exactly until someone
        adds a ``break`` for a timeout or a lost peer. That is the change most
        likely to be made in a hurry, on the day it matters most.

        Checked against the *signed* ``num_sub_games`` rather than against
        whatever the artifact happens to say, because the artifact's count is
        derived from the same short list that is the bug.
        """
        signed = int(self.config.num_sub_games)
        played = int(result.get("num_sub_games", 0) or 0)
        if played == signed:
            return ""
        return (f"refusing to send an incomplete report: {played} sub-game(s) recorded "
                f"against the signed num_sub_games of {signed}")

    def send_result(self, result: dict[str, Any], dry_run: bool = False,
                    to: str = "") -> DeliveryReceipt:
        """Send one result report. ``dry_run`` composes without delivering.

        ``to`` redirects a FRIENDLY to the opposing team and away from the
        lecturer; a counted series refuses it. See
        :mod:`p2pchase.services.friendly_recipient`.
        """
        attachment_name = f"result_{result.get('game_id', 'game')}.json"
        opponent = opponent_in_game_id(str(result.get("game_id", "")),
                                       self.config.group_id)
        recipient, refusal = friendly_recipient.resolve(self.config, opponent, to)
        if refusal:
            LOGGER.error("%s", refusal)
            return DeliveryReceipt(False, "", self.subject(result), attachment_name,
                                   reason=refusal)
        # The subject depends on who is reading it, so it cannot be computed
        # before `resolve` has said who that is. It was, and the effect was a
        # receipt that named one subject while `compose` put a different one in
        # the message -- the mail correct, the record of it wrong. A dry run
        # printed the wrong answer with complete confidence, which is the only
        # thing a dry run exists to prevent.
        subject = self.subject(result, recipient)
        raw, attachment_name = self.compose(result, recipient)

        short = self.incompleteness(result)
        if short and not dry_run:
            LOGGER.error("%s", short)
            return DeliveryReceipt(False, recipient, subject, attachment_name, reason=short)

        if dry_run or not self.config.email.get("enabled", False):
            reason = "dry run" if dry_run else "email.enabled is false in setup.json"
            LOGGER.info("report composed but NOT sent (%s): %s", reason, subject)
            return DeliveryReceipt(False, recipient, subject, attachment_name, reason=reason)

        try:
            response = self.gatekeeper.execute(
                gmail_sender.send_raw, raw, gate_label="gmail.send"
            )
        except Exception as error:  # noqa: BLE001 -- reported, never swallowed silently
            LOGGER.error("report delivery failed: %s: %s", type(error).__name__, error)
            return DeliveryReceipt(False, recipient, subject, attachment_name,
                                   reason=f"{type(error).__name__}: {error}")

        message_id = str(response.get("id", "")) if isinstance(response, dict) else ""
        LOGGER.info("report delivered to %s (id=%s)", recipient, message_id)
        return DeliveryReceipt(True, recipient, subject, attachment_name, message_id)

    def send_result_file(self, path: Path | str, dry_run: bool = False,
                         to: str = "") -> DeliveryReceipt:
        """Load a written result artifact and send it."""
        import json

        with Path(path).open("r", encoding="utf-8") as handle:
            return self.send_result(json.load(handle), dry_run=dry_run, to=to)
