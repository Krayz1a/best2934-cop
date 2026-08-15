"""Inverting a book-model trail back to the cell it was deposited from.

Every field here is built by this module's own arithmetic rather than
transcribed, for the same reason the registered scent examples are: it makes
the test a test of the physics and not of the typing.

Real received fields are deliberately NOT embedded. They are another team's
wire traffic and both our repositories are public -- the capture that measured
this writes outside them on purpose. The wire validation lives beside the
capture; what is asserted here is the arithmetic it relies on.
"""

from __future__ import annotations

import pytest

from p2pchase.domain.smell import BOOK_FIGURE_KERNEL
from p2pchase.domain.trail_inversion import (
    _predict as predict,
)
from p2pchase.domain.trail_inversion import (
    deposit_centre,
    fit_quality,
    reachable_from,
)


def _deposit(previous, centre):
    return predict(previous, centre, BOOK_FIGURE_KERNEL, 0.9, 0.10)


def test_a_single_deposit_is_recovered_exactly():
    field = _deposit({}, (3, 3))

    assert deposit_centre({}, field, BOOK_FIGURE_KERNEL) == (3, 3)


def test_the_recovered_centre_fits_with_no_residual():
    field = _deposit({}, (2, 4))

    assert fit_quality({}, field, (2, 4), BOOK_FIGURE_KERNEL) == pytest.approx(0.0)


def test_a_deposit_onto_a_saturated_trail_is_still_recovered():
    """The case the argmax and the delta both get wrong.

    After several deposits the centre is pinned at the 0.9 ceiling and cannot
    rise, so the largest increase sits out on the ring -- one to two cells away
    from the truth. Fitting the kernel is unaffected because it models the clamp.
    """
    trail = {}
    for centre in ((3, 3), (3, 3), (3, 3), (3, 4)):
        trail = _deposit(trail, centre)
    saturated = _deposit(trail, (3, 5))

    assert deposit_centre(trail, saturated, BOOK_FIGURE_KERNEL) == (3, 5)


def test_the_argmax_of_the_delta_is_not_the_answer():
    """Pin the failure mode itself, so a future simplification cannot return.

    This asserts the naive reading is WRONG on a saturated field -- if it ever
    becomes right, the model changed and this module's reason to exist changed
    with it.
    """
    trail = {}
    for _ in range(6):
        trail = _deposit(trail, (3, 3))
    observed = _deposit(trail, (3, 4))

    rise = {k: observed[k] - trail.get(k, 0.0) for k in observed}
    peak = max(rise, key=lambda k: (rise[k], k))

    assert peak != "3,4"
    assert deposit_centre(trail, observed, BOOK_FIGURE_KERNEL) == (3, 4)


def test_a_walked_trail_recovers_as_a_legal_path():
    """Consecutive recoveries must move at most one cell, as a thief does."""
    walk = [(1, 1), (1, 2), (2, 2), (3, 2), (3, 3), (3, 3), (4, 3)]
    trail, recovered = {}, []
    for centre in walk:
        observed = _deposit(trail, centre)
        recovered.append(deposit_centre(trail, observed, BOOK_FIGURE_KERNEL))
        trail = observed

    assert recovered == walk
    assert all(max(abs(a[0] - b[0]), abs(a[1] - b[1])) <= 1
               for a, b in zip(recovered, recovered[1:], strict=False))


def test_an_empty_field_reads_as_no_reading():
    """None is "no reading", never "they stood still"."""
    assert deposit_centre({}, {}, BOOK_FIGURE_KERNEL) is None


def test_a_malformed_cell_key_does_not_crash_the_fit():
    field = dict(_deposit({}, (3, 3)))
    field["not-a-cell"] = 0.5

    assert deposit_centre({}, field, BOOK_FIGURE_KERNEL) == (3, 3)


def test_the_lag_turns_one_cell_into_five():
    assert sorted(reachable_from((3, 3))) == [(2, 3), (3, 2), (3, 3), (3, 4), (4, 3)]


def test_the_reachable_set_is_clipped_to_the_board():
    """A corner has three, not five -- the board is not wrapped."""
    assert sorted(reachable_from((0, 0))) == [(0, 0), (0, 1), (1, 0)]


def test_no_reading_reaches_nowhere():
    assert reachable_from(None) == []
