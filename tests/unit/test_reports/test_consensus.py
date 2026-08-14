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

from p2pchase import constants
from p2pchase.reports import consensus
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


# ------------------- the five-key row, against the reference's own bytes
#: The reference's published sample run, `docs/sample-run/result_segal-police
#: -team-vs-segal-thief-team.json`, transcribed. Inlined for the same reason as
#: the fixture above: the suite must pass without a clone of that repo.
REFERENCE_SAMPLE_GAME_ID = "segal-police-team-vs-segal-thief-team"
REFERENCE_SAMPLE_AGGREGATE = {
    "total_score": {"segal-police-team": 20, "segal-thief-team": 5},
    "sub_games_won": {"segal-police-team": 1, "segal-thief-team": 0},
    "ties": 0,
    "winner_group": "segal-police-team",
    "series_tie": False,
}
REFERENCE_SAMPLE_ROW = {
    "sub_game_number": 1,
    "roles": {"segal-thief-team": "thief", "segal-police-team": "police"},
    "result": "capture",
    "winner_group": "segal-police-team",
    "score": {"segal-thief-team": 5, "segal-police-team": 20},
}
#: `mutual_agreement.sha256` as published in that artifact.
REFERENCE_SAMPLE_SIGNATURE = \
    "31d678dadbd226dcb1ad87848386416702dcf0735746d7c812350ebc69cbdc81"


def test_the_trimmed_row_reproduces_the_reference_sample_artifact():
    """Five keys, proven rather than argued.

    We hashed a sixth, ``tie``, until 2026-08-14. The argument for it was good
    -- two honest teams must agree a sub-game was tied -- and it was still
    wrong, because agreeing on a fact and hashing it are different questions
    and only the second one has to match byte for byte.

    This asserts against the reference's own published settlement hash, which
    is the only authority that settles it: our digest either reproduces what
    the lecturer's implementation produced for its own sample run, or our
    reports disagree with every team that plays it.
    """
    signature = interop_signature({
        "game_id": REFERENCE_SAMPLE_GAME_ID,
        "aggregate": REFERENCE_SAMPLE_AGGREGATE,
        "sub_games": [REFERENCE_SAMPLE_ROW],
    })
    assert signature == REFERENCE_SAMPLE_SIGNATURE


def test_hashing_tie_as_a_sixth_key_would_not_reproduce_it():
    """The negative half, because a scope test that cannot fail proves nothing.

    Without this, the test above would keep passing if someone re-added ``tie``
    to a row the summary builder no longer feeds it -- the exact regression
    shape this pair exists to catch.
    """
    six_key = interop_signature({
        "game_id": REFERENCE_SAMPLE_GAME_ID,
        "aggregate": REFERENCE_SAMPLE_AGGREGATE,
        "sub_games": [{**REFERENCE_SAMPLE_ROW, "tie": False}],
    })
    assert six_key != REFERENCE_SAMPLE_SIGNATURE


def test_the_summary_builder_emits_exactly_those_five_keys():
    """End to end: the fix has to hold where the rows are actually built."""
    outcome = {"sub_game_number": 1, "roles": {"a": "cop", "b": "thief"},
               "result": "capture", "winner_group": "a", "tie": False,
               "score": {"a": 20, "b": 5}}
    summary = interop_summary("a-vs-b", [outcome], ["a", "b"])
    assert set(summary["sub_games"][0]) == {"sub_game_number", "roles", "result",
                                            "winner_group", "score"}


# ------------- the whole pipeline, against the kit's filed pairing artifact
#: `examples/pairing-artifacts/result_team-aleph-vs-team-bet.json`, regenerated
#: by the kit on 2026-08-13 when the five-key scope was restored. Six sub-games
#: with alternating roles and both outcome kinds, so it exercises the row
#: builder rather than one hand-picked case.
KIT_PAIRING_GAME_ID = "team-aleph-vs-team-bet"
KIT_PAIRING_SIGNATURE = \
    "f47666a35230d0327f2136cb425a421c2b9035ab8e97b823d4a7943e69a15dbf"
#: The same artifact's *pre-fix* digest, published 2026-08-04 and withdrawn.
KIT_PAIRING_SIX_KEY_SIGNATURE = \
    "0c5a4028b30e69400b93d19178fe56f36abcf5db30bba05bf723e712185bdfe9"


def _kit_rows() -> list[dict[str, object]]:
    """The artifact's six sub-games, in *our* outcome shape."""
    rows = []
    for number in range(1, 7):
        police, thief = ("team-aleph", "team-bet") if number % 2 else \
                        ("team-bet", "team-aleph")
        capture = number % 2 == 1
        rows.append({
            "sub_game_number": number,
            "roles": {police: "police", thief: "thief"},
            "result": "capture" if capture else "survival",
            "winner_group": police if capture else thief,
            "tie": False,
            "score": {police: 20, thief: 5} if capture else {thief: 10, police: 5},
        })
    return rows


def test_our_pipeline_reproduces_the_kit_pairing_artifact_digest():
    """End to end, on somebody else's filed bytes -- the only test that counts.

    Everything upstream has to be right at once for this to pass: the five-key
    row, the lower-case ``police``/``capture`` values, the aggregate's five
    scoring keys with the league's extra columns excluded, and the spaced
    serialization. Any one of them wrong and two honest teams file reports that
    contradict each other, which under rule 35 scores both of them zero.
    """
    summary = interop_summary(KIT_PAIRING_GAME_ID, _kit_rows(),
                              ["team-aleph", "team-bet"])
    assert summary["aggregate"]["total_score"] == {"team-aleph": 90, "team-bet": 30}
    assert interop_signature(summary) == KIT_PAIRING_SIGNATURE


def test_the_withdrawn_six_key_digest_is_reproducible_and_is_not_ours():
    """Pins the *wrong* answer too, so the fix cannot silently regress.

    A team that calibrated on the kit between 2026-08-04 and 08-13 built a
    signer that produces the second value. Recomputing it here proves our row
    is the one the artifact was regenerated to, not merely that some hash
    matches something.
    """
    summary = interop_summary(KIT_PAIRING_GAME_ID, _kit_rows(),
                              ["team-aleph", "team-bet"])
    six_key = dict(summary, sub_games=[{**row, "tie": False}
                                       for row in summary["sub_games"]])
    assert interop_signature(six_key) == KIT_PAIRING_SIX_KEY_SIGNATURE
    assert interop_signature(summary) != KIT_PAIRING_SIX_KEY_SIGNATURE


# ------------------------------------------------------- the forfeit spelling
def test_a_forfeit_is_spelled_timeout_in_the_league_row():
    """Our word for the category, in a slot that wants their word for the value.

    The reference's ``domain/protocol.py`` types the field as
    ``"capture" | "survival" | "timeout"``; "technical loss" appears only in its
    ``domain/scoring.py``, naming the *category* that timeout, tamper_forfeit
    and stopped all fall into at 0/0. So ``technical_loss`` was a category name
    in a value slot, and it went out unmapped on every report we filed.

    Harmless on a clean series, and precisely what bites on a forfeit -- the one
    ending where the two teams can least afford a spelling argument, because at
    least one of them has stopped answering. Confirmed with imreeyal on league
    issue #45 before mapping it rather than guessed at.
    """
    assert consensus.league_result(constants.OUTCOME_TECHNICAL_LOSS) == "timeout"


def test_the_two_endings_that_already_agreed_are_left_alone():
    for outcome in (constants.OUTCOME_CAPTURE, constants.OUTCOME_SURVIVAL):
        assert consensus.league_result(outcome) == outcome


def test_an_ending_we_do_not_recognise_passes_through_rather_than_vanishing():
    """A value we cannot map is a disagreement to see, not one to hide. Blanking
    it would file a row whose result field says nothing at all."""
    assert consensus.league_result("resigned") == "resigned"
