"""A series index must be derivable, not whatever each repository counted.

Against gal-roy1 our cop and thief repositories each numbered their own
sub-games from 1, so a six-sub-game series carried the indices 1, 1, 2, 2, 3,
3. Totals were unaffected -- sums do not care about labels -- but
`mutual_agreement` scope covers the per-sub-game rows, so two teams could agree
on 75-35 and still fail a row-by-row join. Agreeing on the score while
disagreeing about the game is the ambiguity rule 35 feeds on.

The position is derived from the pairing's declared role convention via
``cop_group``, the same function that assigns the roles, so both peers reach it
from the two group ids alone with nothing to exchange.

The property that matters most here is the *no-op*: a series already numbered
1..N must come through untouched. imreeyal's numbering was already correct and
has been verified four-way against their independent recomputation; a change
that silently renumbered it would break a settled result to fix an unsettled
one.
"""

from __future__ import annotations

import pytest

from p2pchase.reports.series_assembly import canonical_indices


def _log(number, role):
    return {"summary": {"sub_game_number": number, "role": role}}


ALTERNATING = [_log(1, "police"), _log(2, "thief"), _log(3, "police"),
               _log(4, "thief"), _log(5, "police"), _log(6, "thief")]

COLLIDED = [_log(1, "police"), _log(1, "thief"), _log(2, "police"),
            _log(2, "thief"), _log(3, "police"), _log(3, "thief")]


@pytest.mark.parametrize("convention", ["odd_even", "first_half"])
def test_a_complete_series_is_never_renumbered(convention):
    """The no-op. A settled result must not move because of a fix for another."""
    assert canonical_indices(ALTERNATING, "best2934", "imreeyal", convention) == [
        1, 2, 3, 4, 5, 6]


def test_the_imreeyal_series_specifically_is_untouched():
    """That series was verified four-way; its rows are load-bearing."""
    assert canonical_indices(ALTERNATING, "best2934", "imreeyal", "odd_even") == [
        1, 2, 3, 4, 5, 6]


def test_colliding_numbers_are_derived_under_first_half():
    """gal-roy1's convention: we sort first, so we cop sub-games 1-3."""
    derived = canonical_indices(COLLIDED, "best2934", "gal-roy1", "first_half")

    assert sorted(derived) == [1, 2, 3, 4, 5, 6]
    police = [n for n, log in zip(derived, COLLIDED, strict=True)
              if log["summary"]["role"] == "police"]
    assert police == [1, 2, 3]


def test_colliding_numbers_are_derived_under_odd_even():
    """The same collision under the other convention lands on the odd slots."""
    derived = canonical_indices(COLLIDED, "best2934", "imreeyal", "odd_even")

    assert sorted(derived) == [1, 2, 3, 4, 5, 6]
    police = [n for n, log in zip(derived, COLLIDED, strict=True)
              if log["summary"]["role"] == "police"]
    assert police == [1, 3, 5]


def test_the_derived_index_agrees_with_the_role_assignment():
    """Derivation must be the inverse of `cop_group`, not a parallel guess."""
    from p2pchase.domain.roles import cop_group

    derived = canonical_indices(COLLIDED, "best2934", "gal-roy1", "first_half")
    for number, log in zip(derived, COLLIDED, strict=True):
        cops = cop_group("best2934", "gal-roy1", number, 6, "first_half")
        expected = "police" if cops == "best2934" else "thief"
        assert log["summary"]["role"] == expected


def test_both_peers_derive_the_same_slots_whichever_way_the_pair_is_held():
    """Order independence is the property that makes it safe to derive at all."""
    ours = canonical_indices(COLLIDED, "best2934", "gal-roy1", "first_half")
    mirrored = [_log(m, "thief" if log["summary"]["role"] == "police" else "police")
                for m, log in zip([1, 1, 2, 2, 3, 3], COLLIDED, strict=True)]
    theirs = canonical_indices(mirrored, "gal-roy1", "best2934", "first_half")
    assert sorted(ours) == sorted(theirs) == [1, 2, 3, 4, 5, 6]
    assert ours == theirs


def test_a_partial_series_is_still_derived_rather_than_left_colliding():
    """A crashed run leaves fewer logs; the surviving rows must still be distinct."""
    partial = [_log(1, "police"), _log(1, "thief")]

    derived = canonical_indices(partial, "best2934", "gal-roy1", "first_half")

    assert len(set(derived)) == 2


def test_a_single_log_series_needs_no_derivation():
    assert canonical_indices([_log(1, "police")], "best2934", "x", "first_half") == [1]


def test_an_unreadable_role_does_not_silently_claim_a_slot():
    """A role we cannot parse gets 0, which is visibly wrong rather than plausible."""
    odd = [_log(1, "police"), _log(1, "referee")]

    assert canonical_indices(odd, "best2934", "gal-roy1", "first_half")[1] == 0
