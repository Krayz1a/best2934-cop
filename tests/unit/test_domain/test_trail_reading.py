"""Reading a heading out of a pheromone trail.

This is the physical half of lie detection, so its failure modes matter more
than its success case. Two in particular:

* it must refuse to report a heading it cannot see, because a fabricated reading
  becomes a false conviction in the trust estimator;
* it must never report a diagonal, because the board has no diagonal move and a
  claim of "north-east" is not one an opponent could have made.
"""

from __future__ import annotations

import pytest

from p2pchase.domain.trail_reading import (
    DRIFT_DEADBAND,
    displacement_heading,
    opposite_heading,
)


@pytest.mark.parametrize(
    ("before", "after", "expected"),
    [
        ((3.0, 3.0), (3.5, 3.0), "S"),   # row grows downward
        ((3.0, 3.0), (2.5, 3.0), "N"),
        ((3.0, 3.0), (3.0, 3.4), "E"),
        ((3.0, 3.0), (3.0, 2.6), "W"),
    ],
)
def test_the_dominant_axis_of_the_drift_is_reported(before, after, expected):
    assert displacement_heading(before, after) == expected


def test_a_diagonal_drift_resolves_to_its_larger_component():
    """There is no diagonal move, so a diagonal reading would be unanswerable."""
    assert displacement_heading((3.0, 3.0), (3.4, 3.1)) == "S"
    assert displacement_heading((3.0, 3.0), (3.1, 3.4)) == "E"


def test_a_tie_resolves_to_the_row_axis():
    """Arbitrary but fixed: an unstable tie-break would make replays diverge."""
    assert displacement_heading((3.0, 3.0), (3.2, 3.2)) == "S"


def test_drift_below_the_deadband_is_unreadable_not_stationary():
    """We cannot tell "stood still" from "measured nothing" from outside, and
    guessing either way puts a false verdict into the trust estimator."""
    tiny = DRIFT_DEADBAND / 2
    assert displacement_heading((3.0, 3.0), (3.0 + tiny, 3.0 + tiny)) is None
    assert displacement_heading((3.0, 3.0), (3.0, 3.0)) is None


def test_a_missing_measurement_yields_no_reading():
    """The first sample of a match has nothing to compare against."""
    assert displacement_heading(None, (3.0, 3.0)) is None
    assert displacement_heading((3.0, 3.0), None) is None
    assert displacement_heading(None, None) is None


def test_the_deadband_is_adjustable_per_call():
    """A noisier field can be given a wider band without touching the module."""
    assert displacement_heading((3.0, 3.0), (3.1, 3.0), deadband=0.5) is None
    assert displacement_heading((3.0, 3.0), (3.1, 3.0), deadband=0.05) == "S"


@pytest.mark.parametrize(("heading", "reverse"),
                         [("N", "S"), ("S", "N"), ("E", "W"), ("W", "E")])
def test_every_heading_has_a_reverse(heading, reverse):
    assert opposite_heading(heading) == reverse


def test_there_is_nothing_to_reverse_when_nothing_was_read():
    assert opposite_heading(None) is None
    assert opposite_heading("STAY") is None
