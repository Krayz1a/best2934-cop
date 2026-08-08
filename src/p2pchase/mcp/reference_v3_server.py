"""Binding the reference-v3 tools onto our server, and the queues behind them.

Three tools, and none of them may block. That is not a style preference: the
kit's own transport module calls two peers each awaiting the other inside a
handler "the highest-severity failure available in this design", and it is
right. Our own dialect adapter for gal-roy1 answers a turn with a turn, which
works because *their* driver expects a piggybacked reply. A reference-v3 peer
does not: it pushes into our inbox, returns, and polls its own inbox for ours.
Answering their push with a blocking round trip through our engine would put
two peers inside each other's handlers on the first move.

So a handler here does exactly three things -- validate, enqueue, return -- and
:mod:`p2pchase.mcp.reference_v3_driver` drains the queue and pushes our turns
back out. Splitting them per ADR-019 also means the validation and translation
in :mod:`p2pchase.mcp.reference_v3` are testable with no transport at all,
which is how the kit's seven published cases are run against us.

**Validate before enqueue, never after.** The vector requires the decision to
be made before any state change, because a partially applied bad turn cannot be
rolled back and under rule 35 a self-inflicted protocol fault zeroes both teams.
A refused message never reaches the queue.

The argument names are the reference's, including its asymmetry: ``receive_turn``
and ``receive_control`` take ``message``, ``submit_audit`` takes ``payload``.
Copying an inconsistency feels wrong and is correct -- FastMCP matches declared
names only, so a peer that tidies it up is simply unreachable. We learned that
four times in a week.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from . import reference_v3

LOGGER = logging.getLogger(__name__)

#: Registered by :func:`register_reference_v3`. ``negotiate`` is absent on
#: purpose -- we already publish it, and it accepts their ``message`` spelling.
REFERENCE_TOOLS = ("receive_turn", "submit_audit", "receive_control")


@dataclass
class Inboxes:
    """One peer's queues. A handler's whole job is to validate, enqueue, return.

    ``refusals`` is ours rather than the reference's. Their handlers answer
    ``{"ok": true}`` unconditionally, which means a message we rejected leaves
    no trace on either side -- the sender believes it landed and we wait for a
    turn that will never come in a form we accept. Recording the refusal does
    not fix the silence, but it turns "the series stalled" into a line naming
    the field, which is the difference between a diagnosable evening and the
    one we just had.
    """

    turns: deque[dict[str, Any]] = field(default_factory=deque)
    audits: deque[dict[str, Any]] = field(default_factory=deque)
    controls: deque[dict[str, Any]] = field(default_factory=deque)
    #: Signed agreements pushed at us by a reference-v3 peer. Filled by
    #: :meth:`p2pchase.mcp.handlers.PeerHandlers.negotiate` rather than by a
    #: tool of its own, because we publish one ``negotiate`` for every dialect
    #: and the queue has to be fed whichever spelling the caller used.
    #:
    #: It exists because their handshake is a *push*, not a request. Their
    #: client discards our response body entirely, so answering the call --
    #: which is all we did until 2026-08-09 -- tells them nothing at all. See
    #: :mod:`p2pchase.runtime.reference_handshake`.
    agreements: deque[dict[str, Any]] = field(default_factory=deque)
    refusals: list[str] = field(default_factory=list)

    def queue_agreement(self, theirs: Any) -> None:
        """Queue a pushed agreement, ignoring the shapes that are not one.

        An empty body is a probe, not a handshake, and letting one satisfy the
        driver's wait would start a sub-game on terms nobody sent.
        """
        if isinstance(theirs, dict) and theirs:
            self.agreements.append(dict(theirs))

    def clear(self) -> None:
        """Drop anything queued. Used between sub-games.

        A turn pushed by the opponent's *next* peer while we were still settling
        the last sub-game belongs to the next handshake, not to this one.
        """
        for queue in (self.turns, self.audits, self.controls):
            queue.clear()

    # ``agreements`` is deliberately NOT cleared here. A turn belongs to a step
    # and a stale one corrupts the board, which is what this method is for. An
    # agreement belongs to a pairing: the same peer sends the same fourteen
    # terms every sub-game, so consuming yesterday's is harmless, while dropping
    # one that arrived a moment early hangs the next handshake -- and their
    # peer blocks on ours crossing before it will send a single turn. The two
    # errors are not the same size.


def register_reference_v3(mcp: Any, inboxes: Inboxes) -> tuple[str, ...]:
    """Publish the three tools. Returns the names, so a test can assert them."""

    @mcp.tool
    def receive_turn(message: dict[str, Any]) -> dict[str, Any]:
        """Accept one TurnMessage into the queue. Never plays it here."""
        refusal = reference_v3.refuse_turn(message)
        if refusal:
            inboxes.refusals.append(refusal)
            LOGGER.warning("refusing a reference-v3 turn: %s", refusal)
            return {"ok": False, "error": refusal}
        inboxes.turns.append(dict(message))
        return {"ok": True}

    @mcp.tool
    def submit_audit(payload: dict[str, Any]) -> dict[str, Any]:
        """Accept the end-of-sub-game disclosure. Note: ``payload``, not ``message``."""
        refusal = reference_v3.refuse_audit(payload)
        if refusal:
            inboxes.refusals.append(refusal)
            LOGGER.warning("refusing a reference-v3 audit: %s", refusal)
            return {"ok": False, "error": refusal}
        inboxes.audits.append(dict(payload))
        return {"ok": True}

    @mcp.tool
    def receive_control(message: dict[str, Any]) -> dict[str, Any]:
        """Accept a status signal.

        Optional on their wire and it touches no game state, so it is answered
        rather than interpreted. Queued anyway: a peer that bothers to tell us
        something is worth being able to read afterwards, and an unread queue
        costs nothing.
        """
        inboxes.controls.append(dict(message) if isinstance(message, dict) else {})
        return {"ok": True}

    return REFERENCE_TOOLS
