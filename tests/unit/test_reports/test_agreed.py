"""Our summary object, against the opponent's published vectors (rule 35).

The condition gal-roy1 attached to agreeing a shape, and they were right to:
a vector both sides hash tests one side's hasher, never either side's object.
So these build the summary with *our* code from *their* facts and assert the
digest they published -- the direction their vectors could not test.

Every ``totals`` figure is recomputed here from the sub-games rather than
copied from their note. Their own vector B was labelled a tied series and was
70-50; the numbers looked plausible and nobody asserted them. "A test vector
needs its own assertion, not just a plausible construction."
"""

from __future__ import annotations

import pytest

from p2pchase.domain.crypto import canonical_json, sha256_hex
from p2pchase.reports.agreed import agreed_summary, series_totals

US, THEM = "best2934", "gal-roy1"
GROUPS = [US, THEM]


def _sub_game(number: int, us_role: str, result: str, us_score: int, them_score: int,
              winner: str | None):
    """A finished sub-game in *our* internal vocabulary, not the wire's."""
    them_role = "thief" if us_role == "police" else "police"
    return {
        "sub_game_number": number,
        "roles": {US: us_role, THEM: them_role},
        "result": result,
        "winner_group": winner,
        "tie": False,
        "score": {US: us_score, THEM: them_score},
    }


#: gal-roy1's vector C: a genuine tie, so chapter 9 fires. a = b = 2.
VECTOR_C = [
    _sub_game(1, "thief", "capture", 5, 20, THEM),
    _sub_game(2, "thief", "capture", 5, 20, THEM),
    _sub_game(3, "thief", "survival", 10, 5, US),
    _sub_game(4, "police", "capture", 20, 5, US),
    _sub_game(5, "police", "capture", 20, 5, US),
    _sub_game(6, "police", "survival", 5, 10, THEM),
]
VECTOR_C_SHA = "f57c1b859e47c92169f0b7adf07b2bbdf5580e85747dc46b27f56b79ff2aa23d"
WARM_UP_SHA = "4c2cebd17b0ba81027127ea726d5e7fef1d578e26782e7b38b6fb7429d0c2c24"


def test_our_object_reproduces_their_series_digest():
    """The whole point. Our names, our casing, our aggregation -- their hex."""
    summary = agreed_summary("best2934--gal-roy1--series-tie-C", GROUPS, VECTOR_C,
                             with_totals=True)
    assert sha256_hex(canonical_json(summary)) == VECTOR_C_SHA


def test_our_object_reproduces_their_per_sub_game_digest():
    """The during-play shape, which must stay free of ``totals``."""
    summary = agreed_summary("best2934--gal-roy1--warmup1", GROUPS,
                             [_sub_game(1, "thief", "capture", 5, 20, THEM)])
    assert sha256_hex(canonical_json(summary)) == WARM_UP_SHA


def test_the_per_sub_game_object_never_grows_a_totals_key():
    """It is the one shape both teams have byte-verified against each other."""
    summary = agreed_summary("g", GROUPS, VECTOR_C)
    assert "totals" not in summary


def test_chapter_nine_replaces_the_sums_on_a_level_series():
    """The rule the two teams could have implemented differently while both
    looked right. Vector C is the first vector where the two fields differ."""
    totals = agreed_summary("g", GROUPS, VECTOR_C, with_totals=True)["totals"]
    assert totals["scores"] == {US: 65, THEM: 65}
    assert totals["total_score"] == {US: 2, THEM: 2}
    assert totals["series_tie"] is True
    assert totals["winner"] is None


def test_sub_game_draws_and_a_level_series_are_counted_separately():
    """``ties`` counts sub-games that individually drew; ``series_tie`` is the
    chapter-9 condition on the totals. Deriving either from the other is a bug
    this vector is built to expose -- it has ``ties: 0`` and ``series_tie``."""
    totals = agreed_summary("g", GROUPS, VECTOR_C, with_totals=True)["totals"]
    assert totals["ties"] == 0
    assert totals["series_tie"] is True


def test_a_strict_maximum_is_required_to_name_a_winner():
    decided = VECTOR_C[:-1] + [_sub_game(6, "police", "capture", 20, 5, US)]
    totals = agreed_summary("g", GROUPS, decided, with_totals=True)["totals"]
    assert totals["series_tie"] is False
    assert totals["winner"] == US
    assert totals["total_score"] == totals["scores"]


def test_a_technical_loss_is_neither_a_win_nor_a_tie():
    """Rule 6 zeroes both sides; recording it as a tie would pay points for it."""
    games = [_sub_game(1, "police", "technical_loss", 0, 0, None)]
    wired = agreed_summary("g", GROUPS, games)["sub_games"]
    assert wired[0]["result"] == "TECHNICAL_LOSS"
    totals = series_totals(GROUPS, wired)
    assert totals["sub_games_won"] == {US: 0, THEM: 0}
    assert totals["ties"] == 0


@pytest.mark.parametrize("internal,wire", [("police", "COP"), ("thief", "THIEF")])
def test_roles_are_translated_to_the_agreed_casing(internal, wire):
    """Our vocabulary follows the book's Hebrew; the wire does not."""
    games = [_sub_game(1, internal, "capture", 20, 5, US)]
    assert agreed_summary("g", GROUPS, games)["sub_games"][0]["roles"][US] == wire
