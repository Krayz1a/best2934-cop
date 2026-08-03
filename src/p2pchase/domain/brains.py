"""Decision making: the strategy base class and loader (book chapter 6).

The book is explicit that this is where the grade lives, and equally explicit
about one boundary (rule 25): **the language model never decides the move**.
Move selection is pure Python, deterministic and inspectable. The LLM touches
only the rhetorical layer -- the verbal hint -- because blind reliance on a
model invites hallucinated, illegal moves and a technical loss.

Extension point, matching Appendix F Table 22: subclass :class:`BrainBase` (or
one of the role brains), override ``_pick_move`` and -- for the cop --
``_decide_move``, then point ``strategy.brain`` in ``config/<role>/setup.json``
at ``your.module:YourClass``.

Both shipped brains are *belief-driven*: they never read the opponent's true
cell, because the runtime does not have it. They act on the posterior held in
:class:`~p2pchase.domain.belief.BeliefMap`.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Any

from .. import constants
from .board import Coord
from .own_state import OwnState

__all__ = ["BrainBase", "Decision", "load_brain"]


@dataclass
class Decision:
    """One turn's chosen action plus the reasoning we want on the record.

    ``rationale`` and ``features`` are not decoration: they are what makes a
    replayed log explicable months later, and what the analysis notebook reads
    when it asks why a strategy behaved the way it did.
    """

    move: str
    barrier: Coord | None = None
    intent: str = constants.INTENT_TRUTH
    #: The heading the *hint* will assert. Equal to ``move`` when telling the
    #: truth; a different heading when lying. The move itself is sealed in the
    #: commitment and stays truthful either way -- only the sentence deceives.
    claimed_heading: str | None = None
    rationale: str = ""
    features: dict[str, Any] = field(default_factory=dict)

    @property
    def spoken_heading(self) -> str:
        """What the hint should say, defaulting to the truth."""
        return self.claimed_heading or self.move


class BrainBase:
    """Base strategy building block.

    Input:  an :class:`~p2pchase.domain.own_state.OwnState` -- this peer's
            local truth and its posterior over the opponent.
    Output: a :class:`Decision`.
    Setup:  ``config`` -- the agreed game parameters (read-only context);
            ``tuning`` -- this peer's private ``strategy`` section, which is
            where every adjustable weight comes from. Class attributes supply
            only the fallback default (guidelines §7.2 permits defaults for
            parameters, not hard-coded configuration).
    """

    role: str = ""

    def __init__(self, config: dict | None = None, tuning: dict | None = None) -> None:
        self.config = config or {}
        self.tuning = tuning or {}
        self.turn_index = 0

    def _tuned(self, key: str, default: float) -> float:
        """Read a tuning weight from config, falling back to the class default."""
        value = self.tuning.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    # ------------------------------------------------------------- public API
    def decide(self, state: OwnState) -> Decision:
        """Full turn decision. Override ``_decide_move`` to change behaviour."""
        decision = self._decide_move(state)
        self.turn_index += 1
        return decision

    # ---------------------------------------------------------- override here
    def _decide_move(self, state: OwnState) -> Decision:
        """Default: delegate to ``_pick_move`` with no special action."""
        return Decision(move=self._pick_move(state), rationale="base")

    def _pick_move(self, state: OwnState) -> str:
        legal = state.board.legal_moves(state.position)
        return legal[0] if legal else "STAY"

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _candidates(state: OwnState) -> list[tuple[str, Coord]]:
        """Legal (move, resulting cell) pairs from the current position."""
        return [
            (move, state.board.target_of(state.position, move))
            for move in state.board.legal_moves(state.position)
        ]

    @staticmethod
    def _target_cell(state: OwnState) -> Coord | None:
        """Our best single guess at where the opponent is."""
        return state.belief.most_likely()

    @staticmethod
    def _distance(state: OwnState, a: Coord, b: Coord) -> int:
        """Barrier-aware distance, falling back to Manhattan if walled off.

        The fallback adds a full board's worth of penalty so an unreachable
        target always scores worse than any reachable one, without the caller
        having to special-case ``None``.
        """
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


def _default_brain(role: str) -> type[BrainBase]:
    """Import the shipped brains lazily to keep this module dependency-free."""
    from .cop_brain import CopBrain
    from .thief_brain import ThiefBrain

    return CopBrain if role == constants.ROLE_COP else ThiefBrain


def load_brain(role: str, strategy_cfg: dict, config: dict) -> BrainBase:
    """Instantiate the brain named in ``strategy``, else the shipped default.

    Appendix F Table 22: leaving the setting empty runs the built-in heuristic;
    a ``package.module:Class`` value points at your own subclass. Both the
    role-agnostic ``brain`` key and the book's ``police_class`` /
    ``thief_class`` spelling are accepted, so a config written from the book
    verbatim also works.
    """
    legacy_key = "police_class" if role == constants.ROLE_COP else "thief_class"
    dotted = str(strategy_cfg.get("brain") or strategy_cfg.get(legacy_key) or "").strip()
    if not dotted:
        return _default_brain(role)(config, strategy_cfg)

    if ":" not in dotted:
        raise ValueError(
            f"strategy.brain must look like 'package.module:Class', got {dotted!r}"
        )
    module_name, class_name = dotted.split(":", 1)
    brain_cls = getattr(importlib.import_module(module_name), class_name)
    if not issubclass(brain_cls, BrainBase):
        raise TypeError(f"{dotted} does not inherit from BrainBase")
    return brain_cls(config, strategy_cfg)
