"""Win conditions, the score table and the series tie rule (book ch3.5, ch9)."""

from __future__ import annotations

import pytest

from p2pchase import constants
from p2pchase.domain.scoring import ScoreTable, SeriesTally, build_score_table


def test_capture_pays_the_cop_its_maximum():
    award = ScoreTable().award(constants.OUTCOME_CAPTURE)
    assert award == {"police": 20, "thief": 5}


def test_survival_pays_the_thief_its_maximum():
    award = ScoreTable().award(constants.OUTCOME_SURVIVAL)
    assert award == {"police": 5, "thief": 10}


def test_a_technical_loss_zeroes_both_sides():
    """Nobody may profit from stalling an opponent into a timeout."""
    award = ScoreTable().award(constants.OUTCOME_TECHNICAL_LOSS)
    assert award == {"police": 0, "thief": 0}


def test_an_unknown_outcome_is_refused():
    with pytest.raises(ValueError, match="unknown outcome"):
        ScoreTable().award("resigned")


def test_the_winner_role_follows_the_outcome():
    table = ScoreTable()
    assert table.winner_role(constants.OUTCOME_CAPTURE) == "police"
    assert table.winner_role(constants.OUTCOME_SURVIVAL) == "thief"
    assert table.winner_role(constants.OUTCOME_TECHNICAL_LOSS) is None


def test_the_table_is_built_from_the_agreed_config(shared_config):
    table = build_score_table(shared_config)
    assert table.capture_cop == 20
    assert table.tie_score == 2


def test_a_tally_accumulates_across_sub_games():
    tally = SeriesTally("us", "them")
    tally.record({"us": "police", "them": "thief"}, constants.OUTCOME_CAPTURE, ScoreTable())
    tally.record({"us": "thief", "them": "police"}, constants.OUTCOME_SURVIVAL, ScoreTable())
    assert tally.totals == {"us": 30, "them": 10}
    assert tally.wins == {"us": 2, "them": 0}


def test_a_decisive_series_names_its_winner():
    tally = SeriesTally("us", "them")
    tally.record({"us": "police", "them": "thief"}, constants.OUTCOME_CAPTURE, ScoreTable())
    final = tally.finalise()
    assert final["winner_group"] == "us"
    assert final["series_tie"] is False
    assert final["total_score"] == {"us": 20, "them": 5}


def test_a_dead_level_series_pays_both_sides_the_tie_score():
    """No encounter is left without a scoring verdict, and the tie score is
    ADDED to the sums rather than replacing them.

    The book and the reference contradict each other; the course allows either
    with a documented justification, and ours is in the README and in
    :meth:`SeriesTally.finalise`. Pinned as a decision so that changing it back
    has to be deliberate: the two readings score a level series 27 or 2, and an
    opponent computing the other one voids the match for us both (rule 35).
    """
    tally = SeriesTally("us", "them")
    tally.record({"us": "police", "them": "thief"}, constants.OUTCOME_CAPTURE, ScoreTable())
    tally.record({"us": "thief", "them": "police"}, constants.OUTCOME_CAPTURE, ScoreTable())
    final = tally.finalise()
    assert final["series_tie"] is True
    assert final["winner_group"] is None
    assert final["total_score"] == {"us": 27, "them": 27}
    assert final["raw_score"] == {"us": 25, "them": 25}


# --------------------------------------------------------------------------
# The three tie behaviours (pairing constitution, agreed with imreeyal).
# --------------------------------------------------------------------------

def _level_series(tie_rule, rows):
    """A series whose two sides finish level, scored under one tie rule."""
    from p2pchase.domain.scoring import ScoreTable, SeriesTally

    tally = SeriesTally("best2934", "imreeyal", tie_rule=tie_rule)
    table = ScoreTable()
    for a_role, outcome in rows:
        b_role = constants.ROLE_THIEF if a_role == constants.ROLE_COP else constants.ROLE_COP
        tally.record({"best2934": a_role, "imreeyal": b_role}, outcome, table)
    return tally


def test_the_three_tie_rules_are_three_different_answers():
    """Two conformant teams can settle the same level series differently and
    neither is wrong, which is exactly why the rule has to be declared.

    25-25 under each: ours adds to 27, the book's other reading replaces with 2,
    and the reference applies nothing at all because it already paid per row.
    """
    from p2pchase.domain import scoring

    answers = {}
    for rule in scoring.TIE_RULES:
        tally = scoring.SeriesTally("best2934", "imreeyal", tie_rule=rule,
                                    totals={"best2934": 25, "imreeyal": 25})
        answers[rule] = tally.finalise()["total_score"]["best2934"]

    assert answers[scoring.SERIES_ADD] == 27
    assert answers[scoring.SERIES_REPLACE] == 2
    assert answers[scoring.PER_SUBGAME] == 25
    assert len(set(answers.values())) == 3, "three rules, three numbers"


def test_a_level_series_is_still_a_tie_under_every_rule():
    """The adjustment differs; the verdict must not. A rule that turned a draw
    into a win for one side would be a different game, not a different score."""
    from p2pchase.domain import scoring

    for rule in scoring.TIE_RULES:
        result = scoring.SeriesTally("best2934", "imreeyal", tie_rule=rule,
                                     totals={"best2934": 25, "imreeyal": 25}).finalise()
        assert result["series_tie"] is True
        assert result["winner_group"] is None
        assert result["raw_score"] == {"best2934": 25, "imreeyal": 25}, (
            "the untouched sums stay visible beside the adjusted total")


def test_the_report_names_the_rule_it_was_scored_under():
    """Rule 35 turns on two reports agreeing. A total with no rule beside it
    cannot be reconciled with a different total -- it can only be argued about."""
    from p2pchase.domain import scoring

    result = scoring.SeriesTally("best2934", "imreeyal",
                                 tie_rule=scoring.PER_SUBGAME).finalise()
    assert result["tie_rule"] == scoring.PER_SUBGAME


def test_a_technical_loss_is_not_a_drawn_row_under_any_rule():
    """Rule 6 zeroes both sides. Paying it 2 apiece would reward the stall.

    This test replaces one that asserted the opposite. We used to read a drawn
    row off equal payouts, so a technical loss -- 0 to each side -- was paid
    ``tie_score`` under ``per_subgame`` and counted in ``ties``. That turns the
    penalty for an unreachable or crashed peer into 2 points for *both* teams,
    which is precisely the "win on the clock" that rule 6 exists to remove, and
    :mod:`p2pchase.reports.agreed` had said so in as many words the whole time.
    """
    from p2pchase.domain import scoring

    for rule in scoring.TIE_RULES:
        tally = scoring.SeriesTally("best2934", "imreeyal", tie_rule=rule,
                                    totals={"best2934": 0, "imreeyal": 0})
        paid = tally.record({"best2934": constants.ROLE_COP, "imreeyal": constants.ROLE_THIEF},
                            constants.OUTCOME_TECHNICAL_LOSS, scoring.ScoreTable())
        assert paid == {"best2934": 0, "imreeyal": 0}, f"{rule} paid for a technical loss"
        assert tally.ties == 0, f"{rule} counted a technical loss as a drawn row"


def test_per_subgame_pays_a_real_drawn_row_and_adds_nothing_at_the_end():
    """The reference's mechanism: the tie score lands in the row, not at the end.

    Appendix F's permanent values cannot produce a drawn row at all -- 20/5,
    5/10, and a technical loss that is not a draw -- so the row here is made by
    a score table that pays both roles alike. Synthetic on purpose: it exercises
    the mechanism without pretending our engine can generate one.
    """
    from p2pchase.domain import scoring

    level = scoring.ScoreTable(capture_cop=7, capture_thief=7)
    tally = scoring.SeriesTally("best2934", "imreeyal", tie_rule=scoring.PER_SUBGAME,
                                totals={"best2934": 0, "imreeyal": 0})
    paid = tally.record({"best2934": constants.ROLE_COP, "imreeyal": constants.ROLE_THIEF},
                        constants.OUTCOME_CAPTURE, level)
    assert paid == {"best2934": 9, "imreeyal": 9}, "a drawn row pays the tie score in the row"
    assert tally.finalise()["total_score"] == {"best2934": 9, "imreeyal": 9}, (
        "and the series-level step adds nothing on top of it")


def test_the_two_common_rules_agree_only_when_exactly_one_row_drew():
    """The claim we published, corrected, with the arithmetic pinned.

    We told the league that ``series_add`` and ``per_subgame`` "give the same
    answer whenever some sub-game tied". They do not. With *k* drawn rows in a
    level series ``per_subgame`` pays ``2k`` and ``series_add`` pays 2, so they
    agree at k=1 and differ by ``2(k-1)`` after that. Our old test pinned k=1
    and read it as the general case, which is how the overstatement survived
    into a public proposal.
    """
    from p2pchase.domain import scoring

    level = scoring.ScoreTable(capture_cop=7, capture_thief=7)
    gaps = {}
    for k in (1, 2, 3):
        totals = {}
        for rule in (scoring.SERIES_ADD, scoring.PER_SUBGAME):
            tally = scoring.SeriesTally("best2934", "imreeyal", tie_rule=rule)
            for _ in range(k):
                tally.record({"best2934": constants.ROLE_COP, "imreeyal": constants.ROLE_THIEF},
                             constants.OUTCOME_CAPTURE, level)
            totals[rule] = tally.finalise()["total_score"]["best2934"]
        gaps[k] = totals[scoring.PER_SUBGAME] - totals[scoring.SERIES_ADD]

    assert gaps[1] == 0, "one drawn row is the case where the two rules agree"
    assert gaps == {1: 0, 2: 2, 3: 4}, f"expected a 2(k-1) gap, measured {gaps}"


def test_appendix_f_values_have_no_agreeing_region_at_all():
    """Under the permanent table k is always 0, so the two rules always differ.

    Which strengthens the case for declaring the field rather than weakening
    it: there is no series a pair could play that would let them discover the
    disagreement before it decides a counted result.
    """
    from p2pchase.domain import scoring

    rows = [(constants.ROLE_COP, constants.OUTCOME_CAPTURE),
            (constants.ROLE_THIEF, constants.OUTCOME_CAPTURE),
            (constants.ROLE_COP, constants.OUTCOME_TECHNICAL_LOSS)]
    scored = {rule: _level_series(rule, rows).finalise() for rule in
              (scoring.SERIES_ADD, scoring.PER_SUBGAME)}

    assert all(result["ties"] == 0 for result in scored.values()), (
        "no row can draw under 20/5, 5/10 and a technical loss that is not a draw")
    assert scored[scoring.SERIES_ADD]["total_score"] != scored[scoring.PER_SUBGAME]["total_score"]
