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
    #: Ways out at or below which a cell is a trap worth refusing...
    EXIT_MIN_SAFE = 2
    #: ...but only with the believed cop this close. A barrier comes from a cop
    #: standing beside the cell, so a corner with nobody near it is just a cell.
    EXIT_THREAT_RANGE = 3

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
        """Whether a cop close to ``cell`` could seal us into it (rule 47).

        ``reachable_area`` cannot see this. On an open board a corner and a
        centre cell reach nearly the same number of squares, so the two score
        alike right up until the moment the corner is sealed -- and by then it
        is not a scoring question any more. imreeyal walled our thief into
        (6, 6) behind (5, 6) and (6, 5) in all three of our thief sub-games on
        2026-08-14, every time inside seven moves, because the old score walked
        us there and had nothing to say about it.

        **A veto rather than a term in the score, deliberately.** Scoring open
        cells higher is the obvious fix and it is the wrong one: high-exit cells
        are central cells, so the preference pulls the thief *toward* the cop it
        is running from. Measured over sixty seeds a standing exit bonus took
        survival against a wall-happy cop from 59/60 to 6/60 -- and the same
        sweep moved by twenty games between neighbouring weights with no
        monotone trend, which is a chaotic harness being overfitted rather than
        a signal (ADR-025).

        What is not a matter of tuning: a barrier only ever comes from a cop
        standing beside the cell, and a cell with two exits needs two of them.
        So this vetoes the narrow case that actually beat us -- few ways out,
        and a cop believed close enough to spend the walls -- and says nothing
        at all about the rest of the board.
        """
        peak = self._target_cell(state)
        if peak is None:
            return False
        if state.board.manhattan(cell, peak) > self._tuned("exit_threat_range",
                                                           self.EXIT_THREAT_RANGE):
            return False
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
