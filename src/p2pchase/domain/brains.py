"""Decision making: the strategy module (book chapter 6).

The book is explicit that this is where the grade lives, and equally explicit
about one boundary (rule 25): **the language model never decides the move**.
Move selection is pure Python, deterministic and inspectable. The LLM touches
only the rhetorical layer -- the verbal hint -- because blind reliance on a
model invites hallucinated, illegal moves and a technical loss.

Extension point, matching Appendix F Table 22: subclass :class:`BrainBase`
(or the role brains below), override ``_pick_move`` and -- for the cop --
``_decide_move``, then point ``[strategy] police_class`` / ``thief_class`` in
``config/<role>/game.toml`` at your class.

Both brains are *belief-driven*: they never read the opponent's true cell,
because the runtime does not have it. They act on the posterior maintained in
:class:`~p2pchase.domain.belief.BeliefMap`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .. import constants as K
from .board import Coord
from .own_state import OwnState


@dataclass
class Decision:
    """One turn's chosen action plus the reasoning we want on the record."""

    move: str
    barrier: Coord | None = None
    intent: str = K.INTENT_TRUTH
    rationale: str = ""
    features: dict[str, Any] = field(default_factory=dict)


class BrainBase:
    """Base strategy. Subclass and override ``_pick_move`` / ``_decide_move``."""

    role: str = ""

    def __init__(self, config: dict | None = None) -> None:
        self.config = config or {}
        self.turn_index = 0

    # ------------------------------------------------------------- public API
    def decide(self, state: OwnState) -> Decision:
        """Full turn decision. Override ``_decide_move`` to change behaviour."""
        decision = self._decide_move(state)
        self.turn_index += 1
        return decision

    # ---------------------------------------------------------- override here
    def _decide_move(self, state: OwnState) -> Decision:
        """Default: delegate to ``_pick_move`` with no special action."""
        move = self._pick_move(state)
        return Decision(move=move, rationale="base")

    def _pick_move(self, state: OwnState) -> str:
        legal = state.board.legal_moves(state.position)
        return legal[0] if legal else "STAY"

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _candidates(state: OwnState) -> list[tuple[str, Coord]]:
        """Legal (move, resulting cell) pairs from the current position."""
        out = []
        for move in state.board.legal_moves(state.position):
            out.append((move, state.board.target_of(state.position, move)))
        return out

    @staticmethod
    def _target_cell(state: OwnState) -> Coord | None:
        """Our best single guess at where the opponent is."""
        return state.belief.most_likely()

    @staticmethod
    def _distance(state: OwnState, a: Coord, b: Coord) -> int:
        """Barrier-aware distance, falling back to Manhattan if walled off."""
        path = state.board.shortest_path_length(a, b)
        if path is None:
            return state.board.manhattan(a, b) + state.board.geometry.grid_size**2
        return path

    @staticmethod
    def _expected_distance(state: OwnState, cell: Coord, top_n: int = 6) -> float:
        """Belief-weighted distance from ``cell`` to the opponent.

        Chasing only the single most-likely cell is brittle when the posterior
        is flat. Averaging over the top hypotheses, weighted by probability,
        moves us toward the centre of probability mass instead.
        """
        top = state.belief.top(top_n)
        if not top:
            return 0.0
        total = sum(p for _, p in top) or 1.0
        return sum(p * BrainBase._distance(state, cell, c) for c, p in top) / total


class CopBrain(BrainBase):
    """The pursuer, and -- uniquely -- the architect of the arena.

    Two levers:

    * **Movement.** Close the belief-weighted distance to the thief.
    * **Barriers.** On a turn where it forgoes movement the cop may seal one
      cell within one step of itself. That cell is impassable forever, for both
      players. The quota (14 by default) makes every placement a
      resource-management decision.

    The barrier policy is the part worth reading. Greedy walling is actively
    bad: a barrier can cut the cop off from the thief, or hand the thief a new
    corridor. So a placement is only accepted when it (a) measurably shrinks
    the thief's reachable area, (b) does not increase the cop's own distance to
    the thief, and (c) is worth spending a unit of a finite resource at this
    stage of the game. Barriers are held back until the thief is close enough
    that sealing space actually converts into a capture.
    """

    role = K.ROLE_COP

    #: Below this belief-distance the cop starts considering barriers at all.
    BARRIER_ENGAGE_RANGE = 4
    #: Minimum number of cells a barrier must remove from the thief's world.
    BARRIER_MIN_GAIN = 1
    #: Keep this many barriers in reserve for the final squeeze.
    BARRIER_ENDGAME_RESERVE = 3

    def _decide_move(self, state: OwnState) -> Decision:
        target = self._target_cell(state)
        if target is None:
            return Decision(move=self._pick_move(state), rationale="no-belief")

        distance = self._distance(state, state.position, target)
        barrier = self._choose_barrier(state, target, distance)
        if barrier is not None:
            return Decision(
                move="STAY",
                barrier=barrier,
                intent=K.INTENT_TRUTH,  # barrier declarations are always truthful
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
        """Greedy descent on belief-weighted distance, with a tie-break.

        Ties are broken toward the move that keeps the most of the board
        reachable for us -- being the one who gets boxed in is a real risk once
        the cop has been building walls.
        """
        candidates = self._candidates(state)
        if not candidates:
            return "STAY"

        scored = []
        for move, cell in candidates:
            distance = self._expected_distance(state, cell)
            mobility = state.board.reachable_area(cell, limit=40)
            # Standing still is rarely right for a pursuer under a move ceiling.
            idle_penalty = 0.35 if move == "STAY" else 0.0
            scored.append((distance + idle_penalty - 0.01 * mobility, move))

        scored.sort()
        return scored[0][1]

    def _choose_barrier(self, state: OwnState, target: Coord, distance: int) -> Coord | None:
        """Pick a barrier cell, or None to move instead."""
        left = state.board.barriers_left
        if left <= 0:
            return None
        if distance > self.BARRIER_ENGAGE_RANGE:
            # Too far away: a wall here is speculative and wastes the quota.
            return None
        if left <= self.BARRIER_ENDGAME_RESERVE and distance > 2:
            # Hold the reserve for a squeeze we can actually finish.
            return None

        options = state.board.barrier_targets(state.position)
        if not options:
            return None

        before_area = state.board.reachable_area(target)
        before_gap = self._distance(state, state.position, target)

        best: tuple[float, Coord] | None = None
        for cell in options:
            if cell == state.position:
                # Sealing our own cell is legal but strands us; never useful.
                continue
            state.board.barriers.add(cell)
            try:
                after_area = state.board.reachable_area(target)
                after_gap = state.board.shortest_path_length(state.position, target)
            finally:
                state.board.barriers.discard(cell)

            if after_gap is None or after_gap > before_gap:
                # We would be walling ourselves away from the thief.
                continue
            gain = before_area - after_area
            if gain < self.BARRIER_MIN_GAIN:
                continue
            score = gain - 0.5 * (after_gap - before_gap)
            if best is None or score > best[0]:
                best = (score, cell)

        return best[1] if best else None


class ThiefBrain(BrainBase):
    """The evader. Survival, not distance, is the objective.

    Naively maximising distance from the cop is a trap: it walks the thief into
    corners, which is exactly what the cop's barriers are designed to exploit.
    The dominant term here is therefore **reachable area** -- how much of the
    board the thief can still get to. Distance matters, but as a safety margin,
    not as the goal.

    The thief also has to survive a fixed number of steps, so late in a sub-game
    it becomes increasingly willing to trade room for immediate safety: with two
    steps left, not being adjacent to the cop is all that matters.
    """

    role = K.ROLE_THIEF

    #: Weight on open space versus raw distance early in the game.
    AREA_WEIGHT = 1.0
    DISTANCE_WEIGHT = 1.2
    #: Inside this many steps of the survival threshold, play purely safe.
    ENDGAME_WINDOW = 4

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

    def _pick_move(self, state: OwnState) -> str:
        candidates = self._candidates(state)
        if not candidates:
            return "STAY"

        remaining = max(0, state.survival_threshold - state.step)
        endgame = remaining <= self.ENDGAME_WINDOW

        scored = []
        for move, cell in candidates:
            distance = self._expected_distance(state, cell)
            area = state.board.reachable_area(cell, limit=60)

            if endgame:
                # Only immediate safety counts now.
                score = distance * 2.0 + 0.05 * area
            else:
                score = self.DISTANCE_WEIGHT * distance + self.AREA_WEIGHT * (area * 0.25)

            # Adjacency to the believed cop position is close to fatal.
            peak = self._target_cell(state)
            if peak is not None and state.board.manhattan(cell, peak) <= 1:
                score -= 6.0
            # Standing still saturates our own scent field and paints a target.
            if move == "STAY":
                score -= 1.0

            scored.append((score, move))

        scored.sort(reverse=True)
        return scored[0][1]

    def _choose_intent(self, state: OwnState) -> str:
        """Decide whether this turn's hint will be a lie.

        Deception has to be spent, not sprayed. The opponent is running the same
        scent-versus-claim cross-check we are, so a thief that lies every turn
        simply trains the cop to ignore it. We lie when it is most valuable --
        when the cop is close enough for a misdirection to cost it a turn -- and
        tell the truth otherwise to keep the channel credible.
        """
        peak = self._target_cell(state)
        if peak is None:
            return K.INTENT_TRUTH
        distance = self._distance(state, state.position, peak)
        if distance <= 3 and self.turn_index % 2 == 0:
            return K.INTENT_LIE
        return K.INTENT_TRUTH


def load_brain(role: str, strategy_cfg: dict, config: dict) -> BrainBase:
    """Instantiate the brain named in ``[strategy]``, else the shipped default.

    Appendix F Table 22: leaving the section empty runs the built-in heuristic;
    a ``package.module:Class`` value points at your own subclass.
    """
    key = "police_class" if role == K.ROLE_COP else "thief_class"
    dotted = str(strategy_cfg.get(key, "")).strip()
    if not dotted:
        return (CopBrain if role == K.ROLE_COP else ThiefBrain)(config)

    if ":" not in dotted:
        raise ValueError(f"[strategy] {key} must look like 'package.module:Class', got {dotted!r}")
    module_name, class_name = dotted.split(":", 1)
    import importlib

    module = importlib.import_module(module_name)
    brain_cls = getattr(module, class_name)
    if not issubclass(brain_cls, BrainBase):
        raise TypeError(f"{dotted} does not inherit from BrainBase")
    return brain_cls(config)
