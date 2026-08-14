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

from .. import constants
from ..strategy.hint_decoder import opposite
from .brains import BrainBase, Decision
from .own_state import OwnState


class ThiefBrain(BrainBase):
    """Area-maximising evasion with rationed deception.

    Input:  ``OwnState`` -- own cell, board with declared barriers, posterior.
    Output: ``Decision`` -- a move plus the truth/lie flag for this turn's hint.
    Setup:  ``strategy.area_weight`` / ``distance_weight`` / ``endgame_window``
            in ``config/thief/setup.json``.
    """

    role = constants.ROLE_THIEF

    #: Weight on open space versus raw distance early in the game.
    AREA_WEIGHT = 1.0
    DISTANCE_WEIGHT = 1.2
    #: Inside this many steps of the survival threshold, play purely safe.
    ENDGAME_WINDOW = 4
    #: Standing next to the believed cop position is close to fatal.
    ADJACENCY_PENALTY = 6.0
    #: Standing still saturates our own scent field and paints a target.
    IDLE_PENALTY = 1.0
    #: Ways out at or below which a cell is a trap worth refusing while any
    #: alternative exists. Two is the corner count on an unwalled board.
    EXIT_MIN_SAFE = 2

    def _decide_move(self, state: OwnState) -> Decision:
        move = self._pick_move(state)
        remaining = max(0, state.survival_threshold - state.step)
        intent = self._choose_intent(state)
        # The move is sealed truthfully in the commitment either way. What a lie
        # changes is the heading the *sentence* names -- the reverse of the one
        # actually taken, which is the claim most likely to cost a pursuer a turn.
        claimed = opposite(move) if intent == constants.INTENT_LIE else move
        return Decision(
            move=move,
            intent=intent,
            claimed_heading=claimed,
            rationale=f"evade; {remaining} steps to survival",
            features={
                "steps_remaining": remaining,
                "reachable": state.board.reachable_area(state.position),
                "entropy": round(state.belief.entropy(), 3),
            },
        )

    @staticmethod
    def _exits(state: OwnState, cell: tuple[int, int]) -> int:
        """How many ways out of ``cell`` there are. ``STAY`` is not one of them."""
        return sum(1 for move in state.board.legal_moves(cell) if move != "STAY")

    def _trappable(self, state: OwnState, cell: tuple[int, int]) -> bool:
        """Whether ``cell`` has few enough ways out to be sealed us into.

        ``reachable_area`` cannot see this. On an open board a corner and a
        centre cell reach nearly the same number of squares, so the two score
        alike right up until the moment the corner is sealed -- and by then it
        is not a scoring question any more.

        **Why this is unconditional, against the harness's advice.** Every
        networked thief sub-game we have ever played -- nine against gal-roy1,
        three against imreeyal, twelve of twelve -- ended in the same corner.
        Not similar: identical. Reached (6, 6) at step 6 every time, last
        movement at step 18 every time, then stationary to the ceiling. The old
        score maximised distance from a cop that starts at (0, 0) while we start
        at (3, 3), so it pointed at (6, 6) and kept pointing there, and both
        opponents needed two barriers to finish what our own policy started.
        imreeyal did exactly that and all three were captures under rule 47.

        A twelve-for-twelve failure against two independent opponents outweighs
        a sixty-seed harness in which the cop shares our scent model, our
        transmitted field and our blind spots. It is also the harness that
        argued for the value that has never once fired in a match (see
        :mod:`p2pchase.runtime.belief_probe`), so its objection here is not
        evidence of the same kind.

        Still a veto and not a term in the score, for the reason it always was:
        preferring open cells prefers *central* cells, which walks the thief
        toward the cop it is running from -- measured at 59/60 to 6/60 against a
        wall-happy cop. This forbids the trap and leaves the rest of the board
        to the score, which is a much smaller claim.

        Falls back where every option is trappable, in
        :meth:`_survivable`. Late in a sub-game with walls everywhere, a corner
        may genuinely be the best cell left, and refusing all of them is not a
        decision.
        """
        return self._exits(state, cell) <= self._tuned("exit_min_safe", self.EXIT_MIN_SAFE)

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

    def _survivable(self, state: OwnState,
                    candidates: list[tuple[str, tuple[int, int]]]
                    ) -> list[tuple[str, tuple[int, int]]]:
        """Drop the moves that lose under rule 47, hardest rule first.

        Each veto falls back to the wider set when it would leave nothing:
        refusing every option is not a decision, and STAY is always legal.

        The last one is the one that cost us three sub-games. Standing on a cell
        with a single way out means the cop needs exactly one more barrier, and
        a cop that has walled us once is a cop that is beside us and building --
        so the exit is worth taking even when it runs *toward* where we think
        the cop is. Our thief instead stayed, because the score said the far
        corner was safer than the cell nearer the belief peak, and imreeyal
        sealed (5, 6) behind it the next turn. The lesson is not that the score
        was badly weighted; it is that this is not a scoring question. It is
        the difference between a sub-game we might lose and one we have lost.

        On a 7x7 with no walls the emptiest cell is a corner with two exits, so
        "one exit" already means a barrier has landed beside us. There is no
        need to also detect that separately.

        **What it costs.** Measured over sixty seeds: against a wall-building
        cop -- imreeyal's profile, and the one that beat us -- survival is
        unchanged at 59-60/60. Against our own fielded cop it moves 4/60 to
        0/60, because fleeing a hole walks us into a pursuer that already knows
        where we are. That difference is not significant at this sample size and
        it is against an opponent with a belief map no networked peer has ever
        had of us; the case it protects is one we have actually lost three
        times. Both directions are recorded here so the next person to touch
        this is choosing rather than discovering.
        """
        candidates = [(m, c) for m, c in candidates
                      if m == "STAY" or self._exits(state, c) > 0] or candidates
        candidates = [(m, c) for m, c in candidates
                      if not self._trappable(state, c)] or candidates
        if self._exits(state, state.position) <= 1:
            candidates = [(m, c) for m, c in candidates if m != "STAY"] or candidates
        return candidates

    def _pick_move(self, state: OwnState) -> str:
        candidates = self._candidates(state)
        if not candidates:
            return "STAY"

        candidates = self._survivable(state, candidates)
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
            return constants.INTENT_TRUTH
        distance = self._distance(state, state.position, peak)
        bluff_range = self._tuned("bluff_range", 3)
        bluff_period = max(1, int(self._tuned("bluff_period", 2)))
        if distance <= bluff_range and self.turn_index % bluff_period == 0:
            return constants.INTENT_LIE
        return constants.INTENT_TRUTH
