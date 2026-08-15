"""The pursuer, and -- uniquely -- the architect of the arena (book ch6).

The cop has two levers:

* **Movement.** Close the belief-weighted distance to the thief.
* **Barriers.** On a turn where it forgoes movement the cop may seal one cell
  within one step of itself. That cell is impassable forever, for both players.
  The quota (14 by default) makes every placement a resource decision.

The barrier policy is the part worth reading, because greedy walling is
actively bad. A barrier can cut the cop off from the thief, or hand the thief a
fresh corridor. So a placement is accepted only when it (a) measurably shrinks
the thief's reachable area, (b) does not increase the cop's own distance to the
thief, and (c) is worth spending a unit of a finite resource at this stage.
Barriers are held back until the thief is close enough that sealing space
actually converts into a capture.
"""

from __future__ import annotations

from .. import constants
from .board import Coord
from .brains import BrainBase, Decision
from .own_state import OwnState


class CopBrain(BrainBase):
    """Belief-driven pursuit with resource-aware barrier placement.

    Input:  ``OwnState`` -- own cell, board with declared barriers, posterior.
    Output: ``Decision`` -- either a move, or STAY plus a barrier cell.
    Setup:  ``strategy.barrier_engage_range`` / ``barrier_min_gain`` /
            ``barrier_endgame_reserve`` in ``config/police/setup.json``.
    """

    role = constants.ROLE_COP

    #: Below this belief-distance the cop starts considering barriers at all.
    BARRIER_ENGAGE_RANGE = 4
    #: Minimum number of cells a barrier must remove from the thief's world.
    BARRIER_MIN_GAIN = 1
    #: Keep this many barriers in reserve for the final squeeze.
    BARRIER_ENDGAME_RESERVE = 3
    #: Standing still is rarely right for a pursuer under a move ceiling.
    IDLE_PENALTY = 0.35
    #: Weight on keeping our own escape routes open when distances tie.
    MOBILITY_WEIGHT = 0.01

    @staticmethod
    def _target_cell(state: OwnState) -> Coord | None:
        """The fitted deposit when we have one, otherwise the belief peak.

        Overridden here and not on ``BrainBase`` because the thief calls the
        same helper to decide where to *flee from*, and a thief that flees the
        cop's best estimate of the thief is a thief fleeing itself.

        The posterior is not wrong -- it was measured converging to distance 1
        by step 31 -- it is *late*, and 31 is past the point where a 35-step cap
        leaves room to convert. The fit reads the same field and names the cell
        outright. Where both exist the fit wins, because an exact answer beats a
        distribution over the same evidence.

        It is one full turn stale by agreement, so this is deliberately the
        cell they *were* on: a chaser walking at that cell caught every one of
        eight recovered trajectories by step 19, which is the whole reason to
        prefer it. ``None`` stays "no reading" and falls through to the belief.
        """
        if state.opponent_deposit is not None:
            return state.opponent_deposit
        return state.belief.most_likely()

    def _decide_move(self, state: OwnState) -> Decision:
        target = self._target_cell(state)
        if target is None:
            return Decision(move=self._pick_move(state), rationale="no-belief")

        distance = self._distance(state, state.position, target)
        # A barrier costs the whole turn, and the thief spends that turn moving.
        # That trade is worth it against a cloud -- sealing space is how you
        # make an unknown thief findable. Against a cell we have actually
        # FITTED it is a certain step swapped for a speculative one, and the
        # replay says so plainly: chasing with no barriers at all caught 8 of 8
        # recovered trajectories, while the barrier branch burned turns 8, 9
        # and 10 and sealed (4, 5) -- the cell between the cop and the thief --
        # walling off its own approach.
        barrier = (None if state.opponent_deposit is not None
                   else self._choose_barrier(state, target, distance))
        if barrier is not None:
            return Decision(
                move="STAY",
                barrier=barrier,
                intent=constants.INTENT_TRUTH,  # barrier declarations are always truthful
                rationale=f"seal {barrier} to shrink thief space (d={distance})",
                features={"distance": distance, "barriers_left": state.board.barriers_left},
            )

        move = self._pick_move(state)
        return Decision(
            move=move,
            rationale=f"close distance to belief peak {target} (d={distance})",
            features={
                "distance": distance,
                "belief_peak": list(target),
                "entropy": round(state.belief.entropy(), 3),
            },
        )

    def _pick_move(self, state: OwnState) -> str:
        """Greedy descent on distance to the thief, with a tie-break.

        Ties break toward the move that keeps the most board reachable for us --
        being the one who gets boxed in is a real risk for a player who has
        spent the match building walls.

        **Which distance is the whole game.** Against a fitted cell it is the
        distance to that cell; with no fit it stays the belief-weighted
        expectation, which is the honest quantity when the posterior is all we
        have.

        Measured 2026-08-16, replaying the real brain against real recovered
        trajectories: with the expectation alone the cop walked five steps and
        then STAYED on (3, 3) for the remaining 28 while the thief circled at
        distance 2 to 3. That is not a bug in the scoring, it is the scoring
        working: a saturated book-model field leaves the posterior near-uniform
        (entropy 2.2-2.9 on the wire), every move scores alike, and the mobility
        term settles it on the centre of a 7x7 board -- the cell with the most
        board reachable from it. Sitting in the middle is correct under total
        ignorance and ruinous when the field names the thief outright.

        ``_target_cell`` was not enough on its own: it feeds the barrier choice
        and the rationale, and movement never read it. Both arms of the
        experiment caught 0 of 8 until this line changed.
        """
        candidates = self._candidates(state)
        if not candidates:
            return "STAY"

        idle_penalty = self._tuned("idle_penalty", self.IDLE_PENALTY)
        mobility_weight = self._tuned("mobility_weight", self.MOBILITY_WEIGHT)
        fitted = state.opponent_deposit

        scored = []
        for move, cell in candidates:
            distance = (float(self._distance(state, cell, fitted)) if fitted
                        else self._expected_distance(state, cell))
            mobility = state.board.reachable_area(cell, limit=40)
            penalty = idle_penalty if move == "STAY" else 0.0
            scored.append((distance + penalty - mobility_weight * mobility, move))

        scored.sort()
        return scored[0][1]

    def _should_consider_barrier(self, state: OwnState, distance: int) -> bool:
        """Cheap gates, checked before the expensive flood fills."""
        left = state.board.barriers_left
        if left <= 0:
            return False
        # NOT gated on ``distance <= 0``, though every quantity here degenerates
        # when the belief peak lands on our own cell: "the thief's reachable
        # area" becomes *our* area, so sealing our own neighbours scores a
        # maximal gain, and "our distance to the thief" is nought to ourselves,
        # so the guard against a barrier that pushes the thief away cannot fire.
        # That reads exactly like the bug it half is -- and refusing those
        # placements took the capture rate from 1.00 to 0.00 against three of
        # five thieves when measured on 2026-08-12.
        #
        # The reason is rule 46: a barrier on the thief's cell IS a capture. A
        # peak on our own cell means the thief is close and our reading of it is
        # good, and sealing the ring around us is then the cop's most reliable
        # finisher rather than a mistake. The genuine fault was never building
        # the ring; it was building all of it, last exit included, which
        # ``_keeps_us_mobile`` now forbids one cell earlier.
        if distance > self._tuned("barrier_engage_range", self.BARRIER_ENGAGE_RANGE):
            # Too far away: a wall here is speculative and wastes the quota.
            return False
        if left <= self._tuned("barrier_endgame_reserve", self.BARRIER_ENDGAME_RESERVE):
            # Hold the reserve for a squeeze we can actually finish.
            return distance <= 2
        return True

    def _choose_barrier(self, state: OwnState, target: Coord, distance: int) -> Coord | None:
        """Pick a barrier cell, or ``None`` to move instead."""
        if not self._should_consider_barrier(state, distance):
            return None
        options = state.board.barrier_targets(state.position)
        if not options:
            return None

        min_gain = self._tuned("barrier_min_gain", self.BARRIER_MIN_GAIN)
        before_area = state.board.reachable_area(target)
        before_gap = self._distance(state, state.position, target)

        best: tuple[float, Coord] | None = None
        for cell in options:
            if cell == state.position:
                # Sealing our own cell is legal but strands us; never useful.
                continue
            if not self._keeps_us_mobile(state, cell, target):
                continue
            gain, after_gap = self._evaluate(state, cell, target, before_area)
            if after_gap is None or after_gap > before_gap or gain < min_gain:
                continue
            score = gain - 0.5 * (after_gap - before_gap)
            if best is None or score > best[0]:
                best = (score, cell)

        return best[1] if best else None

    @staticmethod
    def _keeps_us_mobile(state: OwnState, cell: Coord, target: Coord) -> bool:
        """Whether we still have somewhere to go once this cell is sealed.

        Belt and braces beside the ``distance <= 0`` gate above. That gate
        removes the one path to self-immurement we have actually observed;
        this removes the rest of them, without needing to enumerate them. A
        pursuer that cannot move cannot capture, whatever else the placement
        scores, so the cheapest possible test -- do we retain one real move --
        is worth the flood fill it saves.

        Sealing our last exit is legal under rule 15 and it is never right --
        with one exception, which is the whole reason this takes ``target``. A
        barrier placed on the thief's own cell IS a capture (rule 46), so it
        ends the sub-game on the spot and what we could have done next turn is
        moot. Refusing that placement to preserve our mobility cost 1.00 -> 0.92
        against two of five thieves before the exception was added.
        """
        if cell == target:
            return True
        state.board.barriers.add(cell)
        try:
            return any(move != "STAY" for move in state.board.legal_moves(state.position))
        finally:
            state.board.barriers.discard(cell)

    @staticmethod
    def _evaluate(state: OwnState, cell: Coord, target: Coord,
                  before_area: int) -> tuple[int, int | None]:
        """Measure a hypothetical barrier, always restoring the board."""
        state.board.barriers.add(cell)
        try:
            after_area = state.board.reachable_area(target)
            after_gap = state.board.shortest_path_length(state.position, target)
        finally:
            state.board.barriers.discard(cell)
        return before_area - after_area, after_gap
