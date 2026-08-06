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
