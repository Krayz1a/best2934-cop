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
        """
        return theirs if self.round < theirs else theirs + 1

    def _absorb(self, turn: TurnMessage) -> dict[str, Any] | None:
        """Apply everything their turn discloses, in the order evidence arrives."""
        self.session.on_commit(turn.step, turn.commit)
        # The hint has to be recorded before the trail is sampled: the trail is
        # the only thing a claim can be checked against, and absorb_scent is
        # where that check happens.
        caught = self.session.on_reveal(
            turn.step, "", turn.hint, turn.barrier_placed, turn.capture_claim)
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

        turn = TurnMessage(
            step=step,
            sender=WIRE_ROLE.get(self.session.role, self.session.role.upper()),
            commit=commitment,
            hint=hint,
            scent_grid=self._trail(),
            barrier_placed=barrier,
            capture_claim=self.session.capture_claim(),
            win_claim=self._survival_claim(),
        )
        self.session.apply_own_step()
        self.session.end_of_turn()
        self.round = step
        return turn.as_dict()

    def _trail(self) -> dict[str, float]:
        """Our lagged field, pushed whole (their model) rather than queried."""
        state = self.session.state
        grid = state.broadcast.transmitted(state.my_scent.grid)
        return {f"{r},{c}": round(v, 6) for (r, c), v in sorted(grid.items())}

    def _survival_claim(self) -> dict[str, Any] | None:
        """Thief only, at the threshold. Nobody else can see this ending."""
        state = self.session.state
        if state.is_cop or not state.survival_reached():
            return None
        self.finished = constants.OUTCOME_SURVIVAL
        return {"type": "survival", "steps": int(state.step)}
