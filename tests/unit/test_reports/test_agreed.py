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
#: Our digest for vector C, which **no longer equals gal-roy1's published
#: number** (``f57c1b85…``). Nothing drifted: we changed the tied-series rule
#: from replacing the sums to adding to them, deliberately and for the reasons
#: in the README, and this vector is the only one of theirs that ties. Every
#: other vector we share with them still reproduces exactly -- the divergence is
#: confined to a level series and does not touch ordinary play.
#:
#: Recorded rather than quietly re-pinned because it is a live obligation: a
#: bilateral agreement changed unilaterally is worth nothing, and gal-roy1 has
#: to recompute or object before any counted series with them.
VECTOR_C_SHA = "bc7375173cc9a7981420732cca2f05c2d9032a8e5cadb18b59803ef8668e91cb"
VECTOR_C_SHA_UNDER_THE_REPLACING_RULE = (
    "f57c1b859e47c92169f0b7adf07b2bbdf5580e85747dc46b27f56b79ff2aa23d")
WARM_UP_SHA = "4c2cebd17b0ba81027127ea726d5e7fef1d578e26782e7b38b6fb7429d0c2c24"


def test_the_series_digest_diverges_from_gal_roy1_only_on_a_tie():
    """The one vector our tied-series change moved, pinned in both directions.

    This used to reproduce gal-roy1's hex exactly and no longer does, because we
    changed what a level series scores. That is a real obligation, not a stale
    fixture: the digest is a *bilateral* agreement and we altered our half of
    it, so they have to recompute or object before any counted series.

    Asserted against both values so neither can be lost -- the number we now
    compute, and the number the agreement was originally struck on.
    """
    summary = agreed_summary("best2934--gal-roy1--series-tie-C", GROUPS, VECTOR_C,
                             with_totals=True)
    ours = sha256_hex(canonical_json(summary))
    assert ours == VECTOR_C_SHA
    assert ours != VECTOR_C_SHA_UNDER_THE_REPLACING_RULE
    assert summary["totals"]["total_score"] == {US: 67, THEM: 67}
    # The sums are untouched, so the tie score applied is visible as the
    # difference rather than baked in.
    assert summary["totals"]["scores"] == {US: 65, THEM: 65}


def test_our_object_reproduces_their_per_sub_game_digest():
    """The during-play shape, which must stay free of ``totals``."""
    summary = agreed_summary("best2934--gal-roy1--warmup1", GROUPS,
                             [_sub_game(1, "thief", "capture", 5, 20, THEM)])
    assert sha256_hex(canonical_json(summary)) == WARM_UP_SHA


def test_the_per_sub_game_object_never_grows_a_totals_key():
    """It is the one shape both teams have byte-verified against each other."""
    summary = agreed_summary("g", GROUPS, VECTOR_C)
    assert "totals" not in summary


def test_a_level_series_adds_the_tie_score_to_the_sums():
    """The rule two teams can implement differently while both look right.

    Vector C is the first vector where ``scores`` and ``total_score`` differ.
    We ADD the tie score; the alternative reading replaces the sums with it.
    The book and the reference disagree, the course allows either with a
    written justification, and ours is in the README.
    """
    totals = agreed_summary("g", GROUPS, VECTOR_C, with_totals=True)["totals"]
    assert totals["scores"] == {US: 65, THEM: 65}
    assert totals["total_score"] == {US: 67, THEM: 67}
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
