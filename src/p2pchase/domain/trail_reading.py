"""Reading a heading out of a pheromone trail (book ch4, ch6.5).

This is the *physical* half of lie detection. The opponent's sentence claims a
direction; this module works out which direction the opponent actually went, by
watching where the centre of its trail drifts between turns.

Why the centre and not the hottest cell: the peak is a single cell and moves in
integer jumps, so it sits still for several turns and then leaps, which reads as
"no movement" followed by "impossible movement". The intensity-weighted centre
moves a little every turn, in proportion to how much fresh scent was laid down
and where -- a small, continuous signal that survives decay.

The reading is deliberately weak evidence. It averages the entire accumulated
trail, so it lags, and a stationary opponent still shows drift as old scent
decays unevenly. That is why :func:`displacement_heading` has a deadband and why
the trust estimator that consumes it moves in small increments rather than
convicting on a single reading.
"""

from __future__ import annotations

#: Drift smaller than this in both axes is treated as no movement at all. It is
#: a fraction of a cell: below it we are reading decay noise, not travel.
DRIFT_DEADBAND = 0.02


def displacement_heading(
    before: tuple[float, float] | None,
    after: tuple[float, float] | None,
    deadband: float = DRIFT_DEADBAND,
) -> str | None:
    """The compass direction a trail's centre moved, or ``None`` if unreadable.

    ``None`` means "no usable reading" -- no earlier measurement to compare
    against, or a drift too small to distinguish from decay. It never means "the
    opponent stood still", because we cannot tell those two apart from outside.

    Only the dominant axis is reported. The board has no diagonal move, so a
    drift of (0.3 south, 0.1 east) is one southward step seen through a lagging
    average, not a diagonal one.
    """
    if before is None or after is None:
        return None
    d_row = after[0] - before[0]
    d_col = after[1] - before[1]
    if abs(d_row) < deadband and abs(d_col) < deadband:
        return None
    if abs(d_row) >= abs(d_col):
        return "S" if d_row > 0 else "N"
    return "E" if d_col > 0 else "W"


def opposite_heading(heading: str | None) -> str | None:
    """The reverse bearing, or ``None`` when there is nothing to reverse."""
    return {"N": "S", "S": "N", "E": "W", "W": "E"}.get(heading or "")
