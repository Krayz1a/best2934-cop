"""Driving one sub-game on the reference-v3 wire (kit SPEC 7.5).

The shape of this dialect is the whole reason it needs its own driver. Every
message is a fire-and-forget push into the opponent's ``receive_turn``, whose
answer is ``{"ok": true}`` and nothing else -- so a turn cannot ride back on a
response the way it does in :class:`~p2pchase.runtime.turn_loop.TurnLoop`, and
"their move arrived" is a *queue* becoming non-empty rather than a call
returning. :mod:`reference_inbox` holds the waiting; this holds the round.

Three of their rules are load-bearing and none of them is ours:

**The thief moves first.** Not the cop, as in our own protocol and gal-roy1's.
A cop that opens here is a move ahead all game and every one of its commitments
is keyed to the wrong round.

**A round is a step, numbered per peer 1..35.** Both sides use the same number
for the same round; neither counts the other's actions into its own chain.

**There is no nil turn.** Their wire cannot express a handover, so the opener
is a real sealed move at step 1 -- see
:func:`~p2pchase.mcp.reference_v3.from_internal`.

The concession is in :mod:`session_terminal`, and is the part worth reading:
losing quietly on this wire desynchronises the result, and rule 35 voids a
match whose two reports disagree.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from .. import constants
from ..domain.protocol import WIRE_ROLE
from ..mcp import reference_v3
from ..shared.peer_config import PeerConfig
from . import opponent_capture, reference_handshake, reference_inbox, session_terminal
from .peer import OpponentFinishedError, PeerOutcome
from .peer_session import PeerSession
from .turn_loop import TurnLoop
from .watchdog import DeadlineExceededError, Watchdog, WatchdogTrippedError

LOGGER = logging.getLogger(__name__)


def now_iso() -> str:
    """A non-empty ISO-8601 timestamp, which their validator hard-requires.

    Generated per message rather than per sub-game. The field is decorative to
    the physics and fatal by its absence: the kit's own sparring peer sends
    ``""`` and is refused by every conformant receiver.
    """
    return datetime.now(UTC).isoformat()


class ReferenceDriver:
    """Plays one sub-game against a peer speaking reference-v3.

    Input:  a live :class:`PeerSession`, an outbound client, and the inbox the
            server side fills (``PeerHandlers.reference_inboxes`` -- the *same*
            object, or every wait expires beside a full queue).
    Output: a :class:`PeerOutcome` and a disclosable chain, exactly as
            :class:`~p2pchase.runtime.peer.PeerRunner` produces.
    """

    def __init__(self, config: PeerConfig, session: PeerSession, client: Any,
                 inboxes: Any, negotiation: Any = None) -> None:
        self.config = config
        self.session = session
        self.client = client
        self.inboxes = inboxes
        #: Used to sign the agreement we push before round 1. Optional only so
        #: the older tests that drive a bare driver keep working; a live match
        #: always has one, and without it we do not handshake at all -- which
        #: is exactly the bug this argument was added to fix.
        self.negotiation = negotiation
        self.loop = TurnLoop(session)
        self.watchdog = Watchdog(timeout_sec=float(config.watchdog_timeout))
        self.turn_timeout = float(config.turn_timeout)
        #: A claim answer we owe them but have not been able to send yet. The
        #: thief acts before their claim arrives, so its honest "no" waits a
        #: round; rule 22 makes the answer compulsory, not optional.
        self.owed: dict[str, Any] | None = None
        #: Whether our one terminal step has gone out. Sealing a second would
        #: put two records past the end of a sub-game the opponent has closed.
        self.terminal_sent = False

    @property
    def we_open(self) -> bool:
        """The thief moves first -- theirs, not ours (SPEC 7.5)."""
        return self.session.role == constants.ROLE_THIEF

    @property
    def sender(self) -> str:
        return WIRE_ROLE.get(self.session.role, self.session.role.upper())

    # --------------------------------------------------------------- outbound
    async def push_turn(self, turn: dict[str, Any]) -> None:
        """Send one turn. A refusal is logged loudly and never raised.

        They answer ``{"ok": false, "error": ...}`` for a message their
        validator rejects, and that is the single most valuable line in the
        whole run: it names the field, and the alternative is a sub-game that
        stalls with no explanation on either side.
        """
        message = reference_v3.from_internal(turn, now_iso())
        answer = await self.client.call("receive_turn", {"message": message})
        if isinstance(answer, dict) and answer.get("ok") is False:
            LOGGER.error("they refused our turn at step %s: %s",
                         message.get("step"), answer.get("error"))

    async def act(self, step: int, response: dict[str, Any] | None) -> None:
        """Seal our move for this round and push it, carrying any owed answer.

        ``claim_response`` is merged onto our own turn rather than sent alone,
        because their wire has no other way home: a cop's claim is answered on
        the thief's next push, or -- when that answer is "yes" -- on the
        terminal one built by :meth:`concede`.
        """
        turn = self.loop.take_turn(step)
        if response is not None:
            turn["claim_response"] = response
        await self.push_turn(turn)

    async def finish(self, step: int, response: dict[str, Any] | None) -> None:
        """The terminal message: one last sealed ``STAY`` carrying what we owe.

        Built by :func:`session_terminal.build_terminal`, which is where the
        three conditions that make it owed are documented.
        """
        turn = session_terminal.build_terminal(
            self.session, self.loop, self.sender, step, response)
        LOGGER.info("terminal step %d: caught=%s", step, self.session.i_am_caught)
        await self.push_turn(turn)

    # ---------------------------------------------------------------- inbound
    async def receive(self, step: int) -> dict[str, Any] | None:
        """Wait for their turn at ``step``, apply it, and return what we owe."""
        message = await reference_inbox.await_turn(
            self.inboxes, step, self.turn_timeout, self.watchdog)
        opponent_capture.note_turn(step, message)
        response = self.loop.absorb(reference_v3.to_internal(message))
        self._read_concession(message)
        return response

    def _read_concession(self, message: dict[str, Any]) -> None:
        """A thief admitting our claim, arriving on its next push.

        Corroborated by :meth:`TurnLoop.concede` against the cell we actually
        claimed -- believing "you caught me" unchecked is the one direction in
        which a false message would pay us.
        """
        answer = message.get("claim_response")
        if isinstance(answer, dict) and answer.get("caught"):
            self.loop.concede(constants.OUTCOME_CAPTURE, answer.get("claim"))

    # ------------------------------------------------------------------ round
    async def play_round(self, step: int) -> bool:
        """One round: both sides act once. True once the sub-game is settled.

        The two branches are the same three actions in the two possible orders,
        and the order is not ours to choose -- the thief opens.
        """
        if not self.we_open:
            response = await self.receive(step)
            if self.loop.finished:
                # Their terminal message arrived in place of a turn. Acting now
                # would push a move into a sub-game both sides have settled.
                return True
            await self.act(step, response)
            return bool(self.loop.finished)

        await self.act(step, self.owed)
        self.owed = None
        if self.loop.finished:
            return True
        response = await self.receive(step)
        if self.session.i_am_caught:
            # Their claim landed on us. The answer is owed *now*, not next
            # round, because there is no next round -- so it rides on a
            # terminal step of its own rather than being dropped.
            self.terminal_sent = True
            await self.finish(step + 1, response)
            self.loop.finished = constants.OUTCOME_CAPTURE
            return True
        self.owed = response
        return bool(self.loop.finished)

    async def wrap_up(self, step: int) -> None:
        """The last message of a sub-game, and which side owes it.

        The thief owes it and the cop waits for it. That asymmetry is not a
        choice: after the final round the thief always meets one of the three
        conditions in :meth:`finish` -- it owes an answer at the very least --
        and the cop meets none of them.

        The cop waiting is the half that matters. Its claim on the final round
        is the one whose answer decides the sub-game, and without this the cop
        settles as survival a game it may have just won, while the thief
        settles it as a capture. Two reports of one game that disagree is
        exactly the shape rule 35 voids for both teams.
        """
        if self.terminal_sent:
            return
        if self.we_open:
            self.terminal_sent = True
            await self.finish(step, self.owed)
            self.owed = None
            return
        if self.loop.finished or self.loop.claimed is None:
            return
        try:
            message = await reference_inbox.await_turn(self.inboxes, step, self.turn_timeout)
        except (DeadlineExceededError, OpponentFinishedError):
            LOGGER.info("no terminal message from %s; settling on our own board",
                        self.session.opponent)
            return
        self._read_concession(message)

    async def handshake(self) -> dict[str, Any]:
        """Cross signed agreements before round 1 (SPEC 7.5, rule 11).

        Their runtime will not send a turn until this has happened in *both*
        directions -- ``exchange_agreement`` pushes and then blocks on its own
        agreements queue. Omitting it does not degrade the match, it deadlocks
        it, and from our side the deadlock is indistinguishable from an
        opponent who simply never moved. See
        :mod:`p2pchase.runtime.reference_handshake`.
        """
        return await reference_handshake.exchange(
            self.negotiation, self.client, self.inboxes, self.session.opponent)

    async def run_sub_game(self) -> PeerOutcome:
        """Play until capture, survival, the move ceiling, or a fault (rule 6)."""
        await self.handshake()
        max_moves = int(self.config.shared["movement_and_barriers"]["max_moves"])
        outcome = constants.OUTCOME_SURVIVAL
        step = 0
        try:
            for step in range(1, max_moves + 1):
                if await self.play_round(step):
                    outcome = self.loop.finished or outcome
                    break
                if self.session.state.survival_reached():
                    break
            await self.wrap_up(step + 1)
            outcome = self.loop.finished or outcome
        except OpponentFinishedError as ending:
            # Routed through the session rather than read straight off the
            # exception, so their claim meets the same rule every other dialect's
            # does (:mod:`opponent_ending`): first ending wins, casing folded,
            # and an *absence* becomes survival here rather than becoming some
            # invented word that no scoring table recognises.
            self.session.on_opponent_finished(str(ending.args[0]))
            outcome = self.session.opponent_finished
            LOGGER.info("they ended sub-game %d at step %d: %s",
                        self.session.sub_game, step, outcome)
        except (DeadlineExceededError, WatchdogTrippedError) as error:
            LOGGER.error("sub-game %d stalled at step %d: %s",
                         self.session.sub_game, step, error)
            outcome = self.loop.finished or constants.OUTCOME_TECHNICAL_LOSS
        audit = await self.exchange_chains(outcome)
        return PeerOutcome(outcome, step, records=self.session.records,
                           opponent_audit=audit)

    # -------------------------------------------------------------- finishing
    async def exchange_chains(self, outcome: str) -> dict[str, Any]:
        """Disclose our nonces, collect theirs, then empty the inbox.

        Best-effort in both directions: a peer that has already exited owes us
        nothing it can still send, and an audit we never receive costs the
        proof rather than the game (rule 36).

        The clear happens *here*, at the very end, and not at the start of the
        next sub-game. Their model is a fresh MCP session per sub-game, so the
        earliest their next turn can arrive is after that session's
        ``negotiate`` -- which is strictly later than this line. Clearing on the
        way in instead would race that opener and drop it, and a thief's step-1
        turn is the one message a whole sub-game hangs on.
        """
        payload = reference_v3.audit_from_records(
            self.sender, self.session.final_reveal(), outcome)
        try:
            await self.client.call("submit_audit", {"payload": payload})
        except Exception as error:  # noqa: BLE001 -- they may simply have gone
            LOGGER.warning("could not submit our audit: %s", error)
        verdict: dict[str, Any] = {}
        try:
            theirs = await reference_inbox.await_audit(self.inboxes, self.turn_timeout)
            verdict = self.session.audit(list(theirs.get("records") or []))
        except DeadlineExceededError:
            LOGGER.warning("no audit arrived from %s; their chain is unverified",
                           self.session.opponent)
        self.inboxes.clear()
        return verdict
