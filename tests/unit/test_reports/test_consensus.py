"""The cross-team settlement digest (rule 35).

Rule 35 voids the match for BOTH teams on contradictory reports, so the digest
that proves agreement is the one place where being right alone is worth nothing.
These tests pin it against another league implementation's published fixtures
rather than against our own expectations -- a digest that only agrees with
itself is exactly the failure being tested for.

The fixture values are transcribed from `copthief-league-protocol`
`vectors/report_consensus.json`. They are inlined rather than read from a clone
so the suite stays hermetic and keeps passing when nobody has that repo.
"""

from __future__ import annotations

from p2pchase.reports.consensus import (
    interop_aggregate,
    interop_canonical,
    interop_signature,
    interop_summary,
)

#: Their fixture, case 1: a Hebrew-keyed report body, floats absent.
THEIR_REPORT = {
    "קבוצה_א": "team-aleph",
    "קבוצה_ב": "team-bet",
    "תוצאה": {"מנצחת": "team-aleph", "ניקוד": [20, 5]},
    "game_uid": "f757f50d-d4f4-17e7-06cf-755905739b16",
    "tokens_total_series": 0,
    "github_commit": "abc1234",
}
THEIR_SIGNATURE = "af661c4101cfe73470794102ab7417b67ef0ea5b8c3bc55b38133ac5f8e95049"


def test_our_settlement_digest_matches_another_implementation():
    """The whole point: two independent implementations, one number.

    If this ever fails, we and every kit-conformant team would file reports
    that disagree about a match we both played correctly, and rule 35 scores
    the pair zero.
    """
    assert interop_signature(THEIR_REPORT) == THEIR_SIGNATURE


def test_the_settlement_form_is_spaced_not_compact():
    """The league's *second* canonical form, and the reason this module exists.

    Seals and configs use the compact form; settlement uses this one. Reusing
    one helper for both is the bug the split is here to prevent, so the
    difference is asserted rather than trusted.
    """
    rendered = interop_canonical({"b": 1, "a": {"d": 4, "c": 3}})
    assert rendered == '{"a": {"c": 3, "d": 4}, "b": 1}'
    assert ", " in rendered and '": ' in rendered


def test_non_ascii_survives_the_settlement_form():
    """``ensure_ascii=False``. Escaping here changes the preimage, and the
    opponent re-hashing a native string would miss on every Hebrew report."""
    assert "מנצחת" in interop_canonical(THEIR_REPORT)
    assert "\\u" not in interop_canonical(THEIR_REPORT)


def _row(number: int, winner: str | None, score: dict[str, int], tie: bool = False):
    return {"sub_game_number": number, "roles": {}, "result": "CAPTURE",
            "winner_group": winner, "tie": tie, "score": score}


def test_a_tied_series_adds_the_tie_score_rather_than_replacing_the_sums():
    """The one difference from our own reading that changes numbers.

    Ours pays a level series ``tie_score`` *instead of* the sums (chapter 9);
    the league convention *adds* it, reported as the reference's own observed
    behaviour. Both describe the same match with different totals, which is the
    rule-35 contradiction. Pinned here so that adopting their spelling is a
    decision on the record and not a drift.
    """
    rows = [_row(1, "a", {"a": 20, "b": 5}), _row(2, "b", {"a": 5, "b": 20})]
    aggregate = interop_aggregate(["a", "b"], rows, tie_score=2)

    assert aggregate["series_tie"] is True
    assert aggregate["winner_group"] is None
    # 25 each from the sub-games, plus the tie score -- not 2 flat.
    assert aggregate["total_score"] == {"a": 27, "b": 27}


def test_a_decided_series_leaves_the_sums_alone():
    rows = [_row(1, "a", {"a": 20, "b": 5}), _row(2, "a", {"a": 20, "b": 5})]
    aggregate = interop_aggregate(["a", "b"], rows, tie_score=2)

    assert aggregate["series_tie"] is False
    assert aggregate["winner_group"] == "a"
    assert aggregate["total_score"] == {"a": 40, "b": 10}
    assert aggregate["sub_games_won"] == {"a": 2, "b": 0}


def test_the_summary_carries_only_what_both_teams_can_derive():
    """A preimage is canonical only if nobody enriches it.

    ``group_ids`` is deliberately absent -- ``game_id`` is built from the sorted
    pair and already names both teams. Adding a field for safety would
    guarantee the mismatch the digest exists to prevent.
    """
    summary = interop_summary("a-vs-b", [], ["b", "a"])
    assert set(summary) == {"game_id", "aggregate", "sub_games"}
    assert "group_ids" not in summary
    assert set(summary["aggregate"]) == {"total_score", "sub_games_won", "ties",
                                         "winner_group", "series_tie"}
