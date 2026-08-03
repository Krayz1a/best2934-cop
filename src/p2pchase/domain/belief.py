"""Bayesian belief over the opponent's position under partial observation.

Book chapters 1, 4 and 6. Neither agent ever sees the true world state, so each
maintains a probability distribution over where the opponent might be and
updates it from two very different kinds of evidence:

  * The **scent map** -- physical, emitted by the mere act of moving, and
    impossible to forge. Strong evidence.
  * The **verbal hint** -- cheap talk, explicitly allowed to be a lie, and
    committed with a truth/lie ``intent`` flag the opponent only discloses at
    the final audit. Weak evidence, and its weight is *learned*.

The trust coefficient is the interesting part. Every turn we compare what the
hint claimed against what the scent actually showed. An opponent whose words
keep contradicting its trail earns a collapsing trust weight, and its future
hints stop moving our belief at all -- the book's "lie detection" worked
example, generalised into a running estimator rather than a one-off check.

This map is what the live GUI renders as a heat map (book ch7). It shows only
LOCAL truth: our own position plus our belief about the opponent. Rendering the
true objective board would be an illegal information advantage (rules 8, 9).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .board import Board, Coord
from .smell import ScentMap

# How sharply a scent reading concentrates belief. Higher = more decisive.
SCENT_SHARPNESS = 6.0
# Probability mass the opponent keeps on its own cell rather than moving.
STAY_PRIOR = 0.2
# Trust starts neutral and is bounded away from both extremes so a lucky streak
# never makes us fully credulous nor permanently deaf.
TRUST_INITIAL = 0.5
TRUST_FLOOR = 0.02
TRUST_CEILING = 0.9
TRUST_LEARNING_RATE = 0.25


@dataclass
class BeliefMap:
    """Posterior over the opponent's cell, plus an adaptive trust estimator."""

    board: Board
    grid: dict[Coord, float] = field(default_factory=dict)
    trust: float = TRUST_INITIAL
    hints_seen: int = 0
    hints_contradicted: int = 0

    def __post_init__(self) -> None:
        if not self.grid:
            self.reset()

    # ------------------------------------------------------------------ setup
    def reset(self, known_start: Coord | None = None) -> None:
        """Uniform prior, or a point mass when the start position is agreed.

        Start positions are negotiated and written into the shared config, so
        at step 0 both sides genuinely know where the other stands. Uncertainty
        only accumulates from there.
        """
        cells = [c for c in self.board.geometry.cells() if self.board.is_passable(c)]
        if known_start is not None:
            self.grid = {known_start: 1.0}
            return
        weight = 1.0 / len(cells) if cells else 0.0
        self.grid = {c: weight for c in cells}

    # ------------------------------------------------------------- prediction
    def predict(self) -> None:
        """Diffuse belief by one opponent turn (the Dec-POMDP transition model).

        The opponent may stay put or step to any passable orthogonal neighbour.
        We do not know which, so mass spreads accordingly.
        """
        nxt: dict[Coord, float] = {}
        for cell, prob in self.grid.items():
            if prob <= 0.0:
                continue
            moves = [m for m in self.board.legal_moves(cell) if m != "STAY"]
            targets = [self.board.target_of(cell, m) for m in moves]
            nxt[cell] = nxt.get(cell, 0.0) + prob * STAY_PRIOR
            if targets:
                share = prob * (1.0 - STAY_PRIOR) / len(targets)
                for t in targets:
                    nxt[t] = nxt.get(t, 0.0) + share
            else:
                # Boxed in: all remaining mass stays where it is.
                nxt[cell] = nxt.get(cell, 0.0) + prob * (1.0 - STAY_PRIOR)
        self.grid = nxt
        self._prune_and_normalise()

    # ------------------------------------------------------------ observation
    def update_from_scent(self, opponent_scent: ScentMap) -> None:
        """Weight belief by the opponent's (unforgeable) trail intensity.

        A cell carrying a fresh, strong trail is far more likely to hold the
        opponent than a silent one. Silence is absence of information, not
        evidence of absence, so cells with no reading keep a small floor weight
        instead of being zeroed.
        """
        if not opponent_scent.grid:
            return
        peak = max(opponent_scent.grid.values())
        if peak <= 0:
            return
        for cell in list(self.grid):
            reading = opponent_scent.intensity(cell) / peak
            likelihood = math.exp(SCENT_SHARPNESS * reading)
            self.grid[cell] *= likelihood
        self._prune_and_normalise()

    def update_from_hint(self, claimed_cells: set[Coord]) -> None:
        """Fold a decoded verbal hint in, weighted by our current trust.

        ``claimed_cells`` is the set of cells consistent with what the opponent
        said. With trust t, a consistent cell is boosted by (1 + t) and an
        inconsistent one damped by (1 - t). At t = 0 the hint is inert, which is
        exactly what a proven liar deserves.
        """
        if not claimed_cells:
            return
        boost = 1.0 + self.trust
        damp = max(1e-3, 1.0 - self.trust)
        for cell in list(self.grid):
            self.grid[cell] *= boost if cell in claimed_cells else damp
        self._prune_and_normalise()

    def score_hint(self, claimed_cells: set[Coord], opponent_scent: ScentMap) -> bool:
        """Cross-check a hint against the trail and adjust trust. True if honest.

        This is the book's worked example: the thief says "I moved north" while
        every gram of scent sits in the south-east. The gap between the claim
        and the physical record is the tell.
        """
        if not claimed_cells or not opponent_scent.grid:
            return True
        total = sum(opponent_scent.grid.values())
        if total <= 0:
            return True
        supporting = sum(opponent_scent.intensity(c) for c in claimed_cells)
        consistency = supporting / total

        self.hints_seen += 1
        honest = consistency >= 0.25
        if not honest:
            self.hints_contradicted += 1

        target = 1.0 if honest else 0.0
        self.trust += TRUST_LEARNING_RATE * (target - self.trust)
        self.trust = min(TRUST_CEILING, max(TRUST_FLOOR, self.trust))
        return honest

    def collapse(self, cell: Coord) -> None:
        """Opponent position disclosed by the protocol: belief becomes certainty."""
        self.grid = {cell: 1.0}

    # ---------------------------------------------------------------- queries
    def most_likely(self) -> Coord | None:
        if not self.grid:
            return None
        return max(self.grid, key=lambda k: self.grid[k])

    def probability(self, cell: Coord) -> float:
        return self.grid.get(cell, 0.0)

    def expected_cell(self) -> Coord | None:
        """Probability-weighted centroid, snapped to the nearest legal cell."""
        if not self.grid:
            return None
        total = sum(self.grid.values())
        if total <= 0:
            return None
        r = sum(c[0] * p for c, p in self.grid.items()) / total
        c_ = sum(c[1] * p for c, p in self.grid.items()) / total
        guess = (int(round(r)), int(round(c_)))
        if self.board.is_passable(guess):
            return guess
        return self.most_likely()

    def entropy(self) -> float:
        """Shannon entropy in bits -- how lost we currently are."""
        return -sum(p * math.log2(p) for p in self.grid.values() if p > 0)

    def top(self, n: int = 5) -> list[tuple[Coord, float]]:
        return sorted(self.grid.items(), key=lambda kv: kv[1], reverse=True)[:n]

    def as_dict(self) -> dict[str, float]:
        return {f"{r},{c}": round(p, 6) for (r, c), p in sorted(self.grid.items()) if p > 1e-6}

    # ---------------------------------------------------------------- internal
    def _prune_and_normalise(self) -> None:
        """Drop impossible cells, renormalise, and never let belief die out."""
        cleaned = {
            cell: prob
            for cell, prob in self.grid.items()
            if prob > 1e-9 and self.board.is_passable(cell)
        }
        total = sum(cleaned.values())
        if total <= 0:
            self.reset()
            return
        self.grid = {cell: prob / total for cell, prob in cleaned.items()}
