"""Waiting on a reference-v3 inbox, and what counts as the message arriving.

Their transport is symmetric push with no response body, so there is nothing to
await directly: our tool has already answered ``{"ok": true}`` and dropped the
message in a queue. Progress therefore means *a specific message appeared*, and
the entire subtlety is in the word specific.

One deadline per EXPECTED message. A duplicate proves the peer is alive and
discharges nothing; so does a turn for a step we have not reached yet. Both are
the shape a retrying peer produces, and treating either as arrival is how a
driver convinces itself the game is progressing while both sides sit still --
rule 6 charges both teams for the stall that follows.

So the three cases are handled differently and on purpose:

* **step == expected** -- taken out of the queue and returned. The only case
  that feeds the watchdog.
* **step < expected** -- dropped. We have already applied that step; applying it
  twice would advance our board on one of their moves counted two times.
* **step > expected** -- left in the queue. A peer running ahead of us is not
  wrong, only early, and its turn is still owed an answer once we get there.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .peer import OpponentFinishedError
from .watchdog import TurnDeadline

LOGGER = logging.getLogger(__name__)

#: How often to re-check the queue. Matches :mod:`peer`'s own poll interval:
#: these are in-process deques, so the cost is a loop iteration, not a request.
POLL_INTERVAL_SEC = 0.05


def take_turn_at(inboxes: Any, step: int) -> dict[str, Any] | None:
    """Remove and return the queued turn for ``step``, dropping stale ones.

    Scans rather than popping the head: the queue is at most a couple of deep,
    and popping blind would discard an early turn we still owe an answer to.
    """
    keep: list[dict[str, Any]] = []
    found: dict[str, Any] | None = None
    while inboxes.turns:
        message = inboxes.turns.popleft()
        arrived = int(message.get("step", -1))
        if found is None and arrived == step:
            found = message
        elif arrived < step:
            LOGGER.info("dropping a turn for step %d; we are already at %d", arrived, step)
        else:
            keep.append(message)
    inboxes.turns.extend(keep)
    return found


async def await_turn(inboxes: Any, step: int, timeout: float,
                     watchdog: Any = None) -> dict[str, Any]:
    """Wait for their turn at ``step``. Raises rather than waiting forever.

    An audit landing instead ends the wait: their chain is how a reference-v3
    peer says it has stopped playing, and there is then no turn coming. Waiting
    out the deadline on a sub-game we already agree is over would book a
    technical loss for both of us over an ending neither side disputes.
    """
    deadline = TurnDeadline(timeout)
    while True:
        message = take_turn_at(inboxes, step)
        if message is not None:
            if watchdog is not None:
                watchdog.beat()
            return message
        if inboxes.audits:
            # Their claim verbatim, including the empty string. Substituting a
            # word for an absence here is the bug :mod:`opponent_ending` was
            # written from: it turns "they said nothing" into a positive claim,
            # and the caller can no longer tell the two apart.
            raise OpponentFinishedError(str(inboxes.audits[0].get("result_claim", "")))
        if inboxes.refusals:
            # Our own validator turned their message away. They answered, so
            # nothing here will ever time out into a useful diagnosis -- the
            # queue is simply empty for a reason only this log knows.
            LOGGER.error("we refused a reference-v3 message: %s", inboxes.refusals[-1])
        if watchdog is not None:
            watchdog.check(f"reference-v3 step {step}")
        deadline.check(f"waiting for their turn at step {step}")
        await asyncio.sleep(POLL_INTERVAL_SEC)


async def await_audit(inboxes: Any, timeout: float) -> dict[str, Any]:
    """Wait for their disclosed chain at the end of a sub-game (rules 18, 36).

    Bounded like everything else. A peer that never audits costs us the proof,
    not the game, so this is the one wait whose expiry the caller may survive.
    """
    deadline = TurnDeadline(timeout)
    while not inboxes.audits:
        deadline.check("waiting for their audit")
        await asyncio.sleep(POLL_INTERVAL_SEC)
    return dict(inboxes.audits.popleft())
