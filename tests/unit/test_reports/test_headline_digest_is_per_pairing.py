"""Which digest answers to `mutual_agreement.sha256` is a pairing term.

Two correct scopes exist. Ours covers `tie` per row and the sorted group ids;
the kit's SPEC-6 scope trims each row to five keys. They produce different
numbers for the same series, and both are right.

So a pairing that compares `sha256` to `sha256` across the two definitions
watches two honest implementations appear to disagree -- at settlement, with
nothing to point at. anrbj666 put it best on league issue #49 when they took
our offer: the headline is the field a grader machine-diffs between two filed
reports, so it must be one number with one meaning.

gal-roy1 adopted *our* definition, so `own` stays the default: an opponent we
already agree with must not be broken to reach one we have not yet played.

Both digests are always published and both always name their scope. Only the
headline moves.
"""

from __future__ import annotations

from p2pchase.reports.result import SubGameOutcome, build_result_artifact

ROWS = [SubGameOutcome(
    sub_game_number=1, roles={"best2934": "police", "them": "thief"},
    started_at="s", ended_at="e", result="capture", winner_group="best2934",
    github_commit={"best2934": "abc"}, tokens={"best2934": 0},
    score={"best2934": 20, "them": 5}, log_files={"best2934": "log.json"},
    audit={"log_verified": True, "tampered": False}, steps=15)]

FINAL = {"total_score": {"best2934": 20, "them": 5},
         "sub_games_won": {"best2934": 1, "them": 0}, "ties": 0,
         "winner_group": "best2934", "series_tie": False}


def _build(headline):
    return build_result_artifact("best2934-vs-them", "uid", ["best2934", "them"],
                                 ROWS, FINAL, {"best2934": 0, "them": 0},
                                 headline_digest=headline)["mutual_agreement"]


def test_the_default_keeps_our_own_form_as_the_headline():
    """gal-roy1 verified this number; a new pairing must not move it."""
    block = _build("own")

    assert "interop_sha256" in block
    assert block["sha256"] != block["interop_sha256"]
    assert "sorted group_ids" in block["scope"]


def test_the_league_term_puts_the_spec_scope_under_sha256():
    """anrbj666's pairing: the headline is the five-key trim."""
    block = _build("league")

    assert block["sha256"] == _build("own")["interop_sha256"]
    assert "SPEC section 6" in block["scope"]


def test_our_own_digest_survives_under_a_named_key_either_way():
    """Nothing is lost by the swap -- only which key answers to `sha256`."""
    own, league = _build("own"), _build("league")

    assert league["own_form_sha256"] == own["sha256"]
    assert "sorted group_ids" in league["own_form_scope"]


def test_both_digests_are_published_under_both_terms():
    for headline in ("own", "league"):
        block = _build(headline)
        digests = {v for k, v in block.items() if k.endswith("sha256")}
        assert len(digests) == 2, f"{headline} published only one digest"


def test_every_digest_names_its_own_scope():
    """Two hashes side by side with no scopes is how a matching pair gets
    compared against a mismatching one."""
    for headline in ("own", "league"):
        block = _build(headline)
        for key in [k for k in block if k.endswith("sha256")]:
            assert block.get(key.replace("sha256", "scope")), f"{key} has no scope"


def test_an_unknown_term_falls_back_to_ours_rather_than_guessing():
    assert _build("nonsense")["sha256"] == _build("own")["sha256"]


def test_the_swap_changes_no_other_field():
    own = build_result_artifact("g", "uid", ["a", "b"], ROWS, FINAL, {},
                                headline_digest="own")
    league = build_result_artifact("g", "uid", ["a", "b"], ROWS, FINAL, {},
                                   headline_digest="league")

    assert {k: v for k, v in own.items() if k != "mutual_agreement"} == \
           {k: v for k, v in league.items() if k != "mutual_agreement"}
