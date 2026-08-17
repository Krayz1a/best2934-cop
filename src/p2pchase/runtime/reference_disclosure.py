"""What we disclose to a reference-v3 peer at the end of a sub-game.

Split out of :mod:`reference_driver` because the sealed step-0 record belongs
here and the driver had no room left for it -- but the better reason is that
"which records cross the wire" is a different question from "how a round is
played", and the answer to the first is the one an auditor reads.

**The step-0 gap this module closes.** The kit's log schema is explicit that
"Step 0 is the signed step-zero record", carried *in the record chain* rather
than as a message of its own -- and the reference-v3 surface bears that out,
publishing ``negotiate``, ``receive_control``, ``receive_turn`` and
``submit_audit`` and no step-0 tool at all. ``receive_control`` is not the
channel either: the kit defines it as ``enable``/``status``/``restart``/``quit``
and says in as many words that it is NOT part of the sealed game record.

Our own :meth:`MatchService.step_zero` has always sealed the record, and
:mod:`network_artifacts` has always written it as record 0 of our local log. It
simply never left the machine: the driver disclosed ``session.final_reveal()``,
which is the move chain alone. anrbj666 read ``opponent_step_zero: null`` in
every window from 2026-08-14 onwards and were right to call it a rule 53
failure -- three days of a declaration that existed only in our own artifacts.

Prepending here and not inside
:func:`~p2pchase.runtime.session_disclosure.final_reveal` is deliberate. That
function feeds the alternating path too, and gal-roy1's verifier has never been
sent an extra record; changing a wire that works to fix one that does not is
how a repair becomes an outage.
"""

from __future__ import annotations

import logging
from typing import Any

from ..mcp import reference_v3
from . import reference_inbox
from .watchdog import DeadlineExceededError

LOGGER = logging.getLogger(__name__)


def audit_payload(session: Any, sender: str, outcome: str,
                  step_zero: dict[str, Any] | None) -> dict[str, Any]:
    """Our chain for their audit, sealed step-0 first when we hold one.

    ``step_zero`` is optional so the older tests that drive a bare driver keep
    working, and so a caller that cannot sign one degrades to the previous
    behaviour rather than crashing at the end of a played sub-game -- losing the
    declaration is a rule 53 problem, losing the audit is a rule 36 one, and
    there is no reason to trade the second for the first.
    """
    records = session.final_reveal()
    if step_zero:
        records = [step_zero, *records]
    return reference_v3.audit_from_records(sender, records, outcome)


async def exchange_chains(client: Any, inboxes: Any, session: Any, sender: str,
                          outcome: str, step_zero: dict[str, Any] | None,
                          turn_timeout: float) -> dict[str, Any]:
    """Disclose our nonces, collect theirs, then empty the inbox.

    Best-effort in both directions: a peer that has already exited owes us
    nothing it can still send, and an audit we never receive costs the proof
    rather than the game (rule 36).

    The clear happens *here*, at the very end, and not at the start of the next
    sub-game. Their model is a fresh MCP session per sub-game, so the earliest
    their next turn can arrive is after that session's ``negotiate`` -- which is
    strictly later than this line. Clearing on the way in instead would race
    that opener and drop it, and a thief's step-1 turn is the one message a
    whole sub-game hangs on.
    """
    payload = audit_payload(session, sender, outcome, step_zero)
    try:
        await client.call("submit_audit", {"payload": payload})
    except Exception as error:  # noqa: BLE001 -- they may simply have gone
        LOGGER.warning("could not submit our audit: %s", error)
    verdict: dict[str, Any] = {}
    try:
        theirs = await reference_inbox.await_audit(inboxes, turn_timeout)
        verdict = session.audit(list(theirs.get("records") or []))
    except DeadlineExceededError:
        LOGGER.warning("no audit arrived from %s; their chain is unverified",
                       session.opponent)
    inboxes.clear()
    return verdict
