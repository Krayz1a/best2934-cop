"""Alternating turns, driven by whoever holds the token (interop item I-7).

Our own protocol is simultaneous: both peers commit, both reveal, both apply.
gal-roy1's is alternating with a turn token, and receiving a ``TurnMessage``
makes it your move. The two are not reconcilable by renaming fields, which is
why :func:`~p2pchase.mcp.interop.InteropAdapter.submit_turn` refused for so long
rather than guessing.

What makes them reconcilable is that a *round* means the same thing in both: one
action from each side, then the trails decay. So this drives one side of a round
at a time -- absorb what arrived, then act -- and the round closes when we reply.
The engine underneath is untouched; :class:`PeerSession` still holds the board,
the posterior and the commit chain, and the same audit runs over the same
records (rule 36).

Nothing here dials out. The whole exchange rides back on the response to
``submit_turn`` as ``reply_turn``, which is what lets a peer that cannot accept
inbound connections still play a full match.
"""

from __future__ import annotations

import logging
from typing import Any

from .. import constants
from ..domain.protocol import WIRE_ROLE
from ..mcp.turn_message import TurnMessage, claim_response, parse_turn
from . import wall_capture
from .peer_session import PeerSession

LOGGER = logging.getLogger(__name__)


class TurnLoop:
    """Plays one side of an alternating match against a driving opponent.

    Input:  their ``TurnMessage``, one per round.
    Output: ours, to ride back as ``reply_turn``.
    Setup:  wraps a live :class:`PeerSession`; holds no board state of its own.
    """

    def __init__(self, session: PeerSession) -> None:
        self.session = session
        #: Rounds in which we have actually acted. A nil turn does not count.
        self.round = 0
        self.finished = ""
        #: The cell our last capture claim named, kept so that a concession can
        #: be *corroborated* rather than merely believed. A cop cannot see the
        #: thief, so "we won" is the one direction where a lie would pay, and
        #: the claim is the only thing our own board can check it against.
        self.claimed: tuple[int, int] | None = None
        #: A barrier of theirs sitting on our cell, carried from their turn to
        #: the end of ours so rule 46 can be judged over the whole round rather
        #: than at one instant of it. See :mod:`wall_capture`.
        self.walled: tuple[int, int] | None = None

    # ----------------------------------------------------------------- inbound
    def receive(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Absorb their turn and answer with ours.

        The answer carries ``claim_response`` at the top level as well as inside
        ``reply_turn``. A cop that has just claimed a cell needs the verdict to
        decide whether the sub-game is over, and making it dig that out of a
        nested turn it might not even parse would be a poor place to be clever.
        """
        turn = parse_turn(payload)
        if turn.is_nil:
            # A handover. Do not advance the round counter -- see turn_message.
            if not self._may_act():
                return self._decline(turn.step)
            LOGGER.info("nil turn from %s: taking the first move", turn.sender)
            return self._answer(step=self.round + 1, response=None)

        response = self._absorb(turn)
        if self.session.i_am_caught:
            # We answered a claim truthfully in the affirmative. There is no
            # next move to make, and the claim response is what tells them so.
            self.finished = constants.OUTCOME_CAPTURE
            return {"ack": True, "step": turn.step, "claim_response": response,
                    "reply_outcome": constants.OUTCOME_CAPTURE}
        return self._answer(step=self._reply_step(turn.step), response=response)

    def absorb(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Apply their turn *without* answering it, returning any claim response.

        Exists for the reference-v3 wire, where absorbing and answering are two
        separate pushes rather than a call and its return value -- and where the
        thief acts first, so half the time the answer is already sent by the
        time their turn arrives. :meth:`receive` keeps both halves together
        because on gal-roy1's dialect they genuinely are one message.
        """
        turn = parse_turn(payload)
        return None if turn.is_nil else self._absorb(turn)

    def concede(self, outcome: str, cell: list[int] | None = None) -> str:
        """Settle the sub-game from the loser's concession (rules 21, 22, 35).

        The cop is the half of this protocol that cannot see its own win. It
        claims a cell, the thief answers truthfully, and until now nothing wrote
        that answer down: ``finished`` was set when *we* were caught, when we
        survived, or when they claimed survival -- never when we captured. So a
        cop that had just won read its own outcome as ``""``, which is what
        gal-roy1 saw from us across two sub-games our cop won.

        A concession is believed only as far as our own board can corroborate
        it. Conceding a capture says *we* won, and that is precisely the
        direction in which a false message would pay, so it is accepted only
        where we actually claimed the cell being conceded. A concession we
        cannot tie to a claim is recorded by the caller and refused here.
        """
        if outcome and outcome.strip().lower() != constants.OUTCOME_CAPTURE:
            self.finished = self.finished or constants.OUTCOME_SURVIVAL
            return self.finished
        if self.claimed is None:
            LOGGER.warning("a capture was conceded that we never claimed: %s", cell)
            return self.finished
        if cell is not None and tuple(int(part) for part in cell) != self.claimed:
            LOGGER.warning("a capture was conceded at %s; we claimed %s", cell, self.claimed)
            return self.finished
        self.finished = constants.OUTCOME_CAPTURE
        return self.finished

    def _may_act(self) -> bool:
        """May we take a turn, or would that be a second move in one round?

        Alternating play lets the first mover be ahead by exactly one. Anything
        more is two of our moves against one of theirs, which is not a desync --
        it is us cheating, and it is worse than the stall that refusing risks.

        ``opponent_steps_seen`` counts turns they have actually *acted* on, so a
        handover does not raise it. That is what makes a repeated nil visible:
        after the first one we are one ahead legitimately, and a second would
        put us two ahead against an opponent who has still never moved.
        """
        return self.round <= self.session.state.opponent_steps_seen

    def _decline(self, step: int) -> dict[str, Any]:
        """Acknowledge a turn we must not act on, and say why.

        Answered rather than raised or ignored. An exception crosses MCP as an
        opaque transport failure and rule 6 charges both teams for the stall, and
        silence is worse still -- the driver would simply wait.
        """
        LOGGER.warning("declining to act at step %s: we are already a move ahead "
                       "(round %d, opponent has acted %d times)",
                       step, self.round, self.session.state.opponent_steps_seen)
        return {"ack": True, "step": step, "acted": False,
                "error": "already a move ahead; send your turn rather than a handover"}

    def _reply_step(self, theirs: int) -> int:
        """Which round our answer belongs to.

        A round is one action from each side, so the two peers share a step
        number for a whole round and only then advance. Whether their turn opens
        our round or closes it depends on whether we have already acted in it:
        the second mover answers *within* their step, the first mover answers in
        the next one.

        Echoing their step unconditionally is the obvious version and is wrong.
        It pins both peers on step 1 forever -- every commitment recorded under
        the same key, each overwriting the last, and an audit that reports five
        forgeries at step 1 because five different payloads were announced
        under one commitment.

        The ``self.round + 1`` floor is the same failure arriving from the other
        side. If a peer ever sends a step we are already past -- a retry, a
        duplicate handover, a driver that numbers rounds differently -- then
        ``theirs + 1`` can land on a step we have *already sealed*, and we would
        announce two different payloads under two different commitments at one
        step number. gal-roy1 reported exactly that against us twice before we
        could reproduce it. Our own step number must be monotonic no matter what
        arrives, because the audit is keyed on it (rules 19, 36).
        """
        return max(theirs if self.round < theirs else theirs + 1, self.round + 1)

    def _absorb(self, turn: TurnMessage) -> dict[str, Any] | None:
        """Apply everything their turn discloses, in the order evidence arrives."""
        self.session.on_commit(turn.step, turn.commit)
        # The hint has to be recorded before the trail is sampled: the trail is
        # the only thing a claim can be checked against, and absorb_scent is
        # where that check happens.
        caught = self.session.on_reveal(
            turn.step, "", turn.hint, turn.barrier_placed, turn.capture_claim)
        self.walled = wall_capture.entering(self.session, turn.barrier_placed)
        if turn.scent_grid:
            self.session.absorb_scent(turn.scent_grid)
        if turn.win_claim:
            LOGGER.info("opponent claims survival at step %s", turn.step)
            self.finished = constants.OUTCOME_SURVIVAL
        if turn.capture_claim is None:
            return None
        return claim_response(turn.capture_claim, bool(caught))

    # ---------------------------------------------------------------- outbound
    def _answer(self, step: int, response: dict[str, Any] | None) -> dict[str, Any]:
        reply = self.take_turn(step)
        answer: dict[str, Any] = {"ack": True, "step": step, "reply_turn": reply}
        if response is not None:
            answer["claim_response"] = response
        return answer

    def take_turn(self, step: int) -> dict[str, Any]:
        """Decide, seal, declare -- and close the round.

        ``capture_claim`` is read between sealing and applying, because it names
        the cell our pending move settles on and that cell does not exist before
        :meth:`~PeerSession.prepare_step` or after
        :meth:`~PeerSession.apply_own_step`.
        """
        commitment = self.session.prepare_step(step)
        hint, barrier = self.session.pending_declaration()
        claim = self.session.capture_claim()
        if claim is not None:
            self.claimed = (int(claim[0]), int(claim[1]))

        turn = TurnMessage(
            step=step,
            sender=WIRE_ROLE.get(self.session.role, self.session.role.upper()),
            commit=commitment,
            hint=hint,
            scent_grid=self.trail(),
            barrier_placed=barrier,
            capture_claim=claim,
            win_claim=self._survival_claim(),
        )
        self.session.apply_own_step()
        # Judged after our move, not before: a thief still on the walled cell at
        # the end of its own round is caught under any reading of I-8 (rule 46).
        if wall_capture.leaving(self.session, self.walled):
            self.finished = constants.OUTCOME_CAPTURE
        self.walled = None
        self.session.end_of_turn()
        self.round = step
        return turn.as_dict()

    def trail(self) -> dict[str, float]:
        """Our lagged field, pushed whole (their model) rather than queried."""
        state = self.session.state
        grid = state.broadcast.transmitted(state.my_scent.grid)
        return {f"{r},{c}": round(v, 6) for (r, c), v in sorted(grid.items())}

    def outcome(self) -> str:
        """How this peer reads the sub-game, including endings nobody announced.

        ``finished`` records an ending we *observed*: a capture either side
        settled, our own survival at the threshold, or a survival they claimed.
        It leaves out the one ending that arrives by nothing happening -- the
        thief running out the clock on a cop who is never told.

        gal-roy1 saw that from the other side on 2026-08-09: our ``agree_result``
        named an outcome on the capture path and nothing on the survival path,
        because their thief simply survived and our cop had no observation to
        write down. A peer that cannot name its own loss cannot agree a result,
        and rule 35 voids a sub-game whose two reports disagree -- including
        when one of them is silent.

        The horizon is symmetric and both boards can see it, so the cop derives
        it rather than waiting to be told. This reports our own defeat, which is
        the point: the truthful answer is the one that agrees with theirs.
        """
        if self.finished:
            return self.finished
        return (constants.OUTCOME_SURVIVAL
                if self.session.state.survival_reached() else "")

    def _survival_claim(self) -> dict[str, Any] | None:
        """Thief only, at the threshold. Nobody else can see this ending."""
        state = self.session.state
        if state.is_cop or not state.survival_reached():
            return None
        self.finished = constants.OUTCOME_SURVIVAL
        return {"type": "survival", "steps": int(state.step)}
