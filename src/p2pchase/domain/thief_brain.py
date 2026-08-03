"""The evader (book ch6). Survival, not distance, is the objective.

Naively maximising distance from the cop is a trap: it walks the thief into
corners, which is exactly what the cop's barriers are designed to exploit. The
dominant term here is therefore **reachable area** -- how much of the board the
thief can still get to. Distance matters, but as a safety margin rather than a
goal.

The thief must survive a fixed number of steps, so late in a sub-game it grows
willing to trade room for immediate safety: with two steps left, not being
adjacent to the cop is the only thing that counts.

Deception is handled here too, and deliberately rationed -- see
:meth:`ThiefBrain._choose_intent`.
"""

from __future__ import annotations

from .. import constants as K
from .brains import BrainBase, Decision
from .own_state import OwnState


class ThiefBrain(BrainBase):
    """Area-maximising evasion with rationed deception.

    Input:  ``OwnState`` -- own cell, board with declared barriers, posterior.
    Output: ``Decision`` -- a move plus the truth/lie flag for this turn's hint.
    Setup:  ``strategy.area_weight`` / ``distance_weight`` / ``endgame_window``
            in ``config/thief/setup.json``.
    """

    role = K.ROLE_THIEF

    #: Weight on open space versus raw distance early in the game.
    AREA_WEIGHT = 1.0
    DISTANCE_WEIGHT = 1.2
    #: Inside this many steps of the survival threshold, play purely safe.
    ENDGAME_WINDOW = 4
    #: Standing next to the believed cop position is close to fatal.
    ADJACENCY_PENALTY = 6.0
    #: Standing still saturates our own scent field and paints a target.
    IDLE_PENALTY = 1.0

    def _decide_move(self, state: OwnState) -> Decision:
        move = self._pick_move(state)
        remaining = max(0, state.survival_threshold - state.step)
        return Decision(
            move=move,
            intent=self._choose_intent(state),
            rationale=f"evade; {remaining} steps to survival",
            features={
                "steps_remaining": remaining,
                "reachable": state.board.reachable_area(state.position),
                "entropy": round(state.belief.entropy(), 3),
            },
        )

    def _score(self, state: OwnState, move: str, cell: tuple[int, int],
               endgame: bool) -> float:
        """Utility of one candidate move. Higher is better."""
        distance = self._expected_distance(state, cell)
        area = state.board.reachable_area(cell, limit=60)

        if endgame:
            score = distance * 2.0 + 0.05 * area
        else:
            score = (
                self._tuned("distance_weight", self.DISTANCE_WEIGHT) * distance
                + self._tuned("area_weight", self.AREA_WEIGHT) * (area * 0.25)
            )

        peak = self._target_cell(state)
        if peak is not None and state.board.manhattan(cell, peak) <= 1:
            score -= self._tuned("adjacency_penalty", self.ADJACENCY_PENALTY)
        if move == "STAY":
            score -= self._tuned("idle_penalty", self.IDLE_PENALTY)
        return score

    def _pick_move(self, state: OwnState) -> str:
        candidates = self._candidates(state)
        if not candidates:
            return "STAY"

        remaining = max(0, state.survival_threshold - state.step)
        endgame = remaining <= self._tuned("endgame_window", self.ENDGAME_WINDOW)

        scored = [(self._score(state, move, cell, endgame), move) for move, cell in candidates]
        scored.sort(reverse=True)
        return scored[0][1]

    def _choose_intent(self, state: OwnState) -> str:
        """Decide whether this turn's hint will be a lie.

        Deception has to be spent, not sprayed. The opponent runs the same
        scent-versus-claim cross-check we do, so a thief that lies every turn
        simply trains the cop to ignore it -- and a hint nobody believes is
        worth nothing when we finally need one. We lie when it is most valuable,
        with the cop close enough for misdirection to cost it a turn, and tell
        the truth otherwise to keep the channel credible.
        """
        peak = self._target_cell(state)
        if peak is None:
            return K.INTENT_TRUTH
        distance = self._distance(state, state.position, peak)
        bluff_range = self._tuned("bluff_range", 3)
        bluff_period = max(1, int(self._tuned("bluff_period", 2)))
        if distance <= bluff_range and self.turn_index % bluff_period == 0:
            return K.INTENT_LIE
        return K.INTENT_TRUTH
