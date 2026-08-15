"""Recover the cell a book-model trail was deposited from.

Under ``multiplicative_book_v1`` the field ACCUMULATES --
``tau' = clamp((1 - rho) * tau + delta, 0, 0.9)`` -- so it is a trail and not a
position. Reading its argmax names the visited path rather than the thief, and
the path saturates: measured across our captured tapes, 7100 cells sat pinned
at the 0.9 ceiling with 6 to 18 cells tied at the maximum in every field.

That is why the peak is useless here and why it is fine under
``subtractive_chebyshev_v1``, whose field decays to a single ring set with one
unique maximum in all 513 grids we hold.

**The delta is not the answer either.** The kernel's centre value is 0.9, which
IS the clamp ceiling, so the centre saturates on the first deposit and can never
increase again; the largest *increase* then jumps out to the ring. Taking the
argmax of the delta violated the one-cell-per-step movement bound on 30% of
transitions, with a hard artefact at exactly speed 2 -- the ring offset.

Fitting the whole kernel, with the clamp modelled rather than ignored, recovers
the deposit exactly. Measured over 264 consecutive transitions of real received
fields: **0 violations of the one-cell bound, median residual 0.0, and speeds
only 0 or 1** -- a legal trajectory at every step.

What this does NOT give you is the thief's current cell. The transmitted field
is held one full turn by agreement (``pheromone_transmit_lag: 1``), so the
recovered centre is where they were, not where they are. A cop still has to
close the gap; it just no longer has to guess the direction.
"""

from __future__ import annotations

from .. import constants

Cell = tuple[int, int]
Field = dict[str, float]


def _predict(previous: Field, centre: Cell, kernel, cap: float, decay: float) -> Field:
    """Decay the whole field once, then deposit ``kernel`` at ``centre``.

    Order matters and is the book's: ``(1 - rho) * tau`` first, deposit second,
    clamp last. Deposit-then-decay reaches different values and is the mistake
    an implementation makes silently, because both orders look right in prose.
    """
    out = {cell: (1.0 - decay) * value for cell, value in previous.items()}
    half = len(kernel) // 2
    for r, row in enumerate(kernel):
        for c, delta in enumerate(row):
            key = f"{centre[0] + r - half},{centre[1] + c - half}"
            out[key] = min(out.get(key, 0.0) + delta, cap)
    return out


def _candidates(observed: Field, half: int) -> set[Cell]:
    """Every cell whose kernel could touch a reported one. Nothing else can."""
    cells: set[Cell] = set()
    for key in observed:
        row, _, column = key.partition(",")
        try:
            r, c = int(row), int(column)
        except ValueError:
            continue
        for dr in range(-half, half + 1):
            for dc in range(-half, half + 1):
                cells.add((r + dr, c + dc))
    return cells


def deposit_centre(previous: Field, observed: Field, kernel,
                   cap: float = constants.PHEROMONE_CENTER_INTENSITY,
                   decay: float = constants.PHEROMONE_DECAY) -> Cell | None:
    """The cell that best explains ``observed`` as one deposit onto ``previous``.

    ``None`` when there is nothing to fit -- an empty field, or a first
    observation with no previous state to have decayed from. ``None`` means "no
    reading", never "they did not move": those are not distinguishable from
    outside, and a caller that conflates them will chase a stale cell forever.

    Ties are broken by the lowest ``(row, column)`` so the answer is
    deterministic. A tie means two deposits explain the field equally well,
    which on a saturated board is common and is exactly why the *residual*
    matters more than the winner -- see :func:`fit_quality`.
    """
    if not observed:
        return None
    best: tuple[float, Cell] | None = None
    for centre in sorted(_candidates(observed, len(kernel) // 2)):
        predicted = _predict(previous, centre, kernel, cap, decay)
        error = sum((predicted.get(key, 0.0) - value) ** 2
                    for key, value in observed.items())
        if best is None or error < best[0]:
            best = (error, centre)
    return None if best is None else best[1]


def fit_quality(previous: Field, observed: Field, centre: Cell, kernel,
                cap: float = constants.PHEROMONE_CENTER_INTENSITY,
                decay: float = constants.PHEROMONE_DECAY) -> float:
    """Sum of squared error for one candidate centre. Zero is an exact fit.

    Worth checking rather than trusting the winner: an exact zero says the
    opponent runs the same arithmetic we do and the recovered cell is their
    real one. A large residual says they do not, and a cop that steers on it
    anyway is steering on a model that does not describe the field it is
    reading.
    """
    predicted = _predict(previous, centre, kernel, cap, decay)
    return sum((predicted.get(key, 0.0) - value) ** 2
               for key, value in observed.items())


def reachable_from(centre: Cell | None, board: int = constants.GRID_SIZE) -> list[Cell]:
    """Where a thief last seen at ``centre`` can be now, given the one-turn lag.

    The move set is N/S/E/W/STAY, so the answer is the four neighbours plus the
    cell itself -- five candidates, clipped to the board. This is the honest
    width of what the lag costs: the field pins the cell exactly, and the delay
    turns one cell into five rather than into a guess.
    """
    if centre is None:
        return []
    steps = ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1))
    return [(centre[0] + dr, centre[1] + dc) for dr, dc in steps
            if 0 <= centre[0] + dr < board and 0 <= centre[1] + dc < board]
