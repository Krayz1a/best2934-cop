"""The posterior and the adaptive trust estimator (book ch1, ch4, ch6)."""

from __future__ import annotations

import pytest

from p2pchase.domain.belief import (
    TRUST_CEILING,
    TRUST_FLOOR,
    TRUST_INITIAL,
    BeliefMap,
)
from p2pchase.domain.board import BoardGeometry
from p2pchase.domain.smell import build_scent_map


@pytest.fixture
def belief(board):
    return BeliefMap(board=board)


@pytest.fixture
def scent(shared_config):
    return build_scent_map(shared_config, BoardGeometry(7))


def test_a_fresh_belief_is_uniform_and_normalised(belief):
    assert sum(belief.grid.values()) == pytest.approx(1.0)
    assert len({round(p, 9) for p in belief.grid.values()}) == 1


def test_an_agreed_start_position_is_certainty_not_belief(belief):
    """Start cells are negotiated, so step 0 carries no uncertainty at all."""
    belief.reset(known_start=(3, 3))
    assert belief.grid == {(3, 3): 1.0}
    assert belief.entropy() == pytest.approx(0.0)


def test_prediction_spreads_mass_and_raises_entropy(belief):
    belief.reset(known_start=(3, 3))
    belief.predict()
    assert sum(belief.grid.values()) == pytest.approx(1.0)
    assert belief.entropy() > 0.0
    assert len(belief.grid) == 5  # the cell itself plus four neighbours


def test_prediction_never_leaks_into_a_barrier(belief, board):
    board.barriers.add((3, 4))
    belief.reset(known_start=(3, 3))
    belief.predict()
    assert (3, 4) not in belief.grid


def test_a_boxed_in_opponent_keeps_all_its_mass(belief, board):
    board.barriers.update({(0, 1), (1, 0)})
    belief.reset(known_start=(0, 0))
    belief.predict()
    assert belief.grid == {(0, 0): pytest.approx(1.0)}


def test_scent_evidence_sharpens_the_posterior(belief, scent):
    belief.reset()
    before = belief.entropy()
    scent.emit((5, 5))
    belief.update_from_scent(scent)
    assert belief.entropy() < before
    assert belief.most_likely() == (5, 5)


def test_an_empty_scent_field_changes_nothing(belief, scent):
    belief.reset()
    snapshot = dict(belief.grid)
    belief.update_from_scent(scent)
    assert belief.grid == snapshot


def test_silence_is_not_evidence_of_absence(belief, scent):
    """A cell with no reading is unknown, not empty -- it keeps a floor weight."""
    belief.reset()
    scent.emit((5, 5))
    belief.update_from_scent(scent)
    assert belief.probability((0, 0)) > 0.0


def test_a_credible_claim_transports_belief_in_the_claimed_direction(belief):
    """The claim is about how the cloud MOVED, so mass travels rather than
    being reweighted in place."""
    belief.collapse((3, 3))
    belief.trust = 0.9
    belief.update_from_hint("N")
    assert belief.probability((2, 3)) == pytest.approx(0.9)
    assert belief.probability((3, 3)) == pytest.approx(0.1)


def test_a_claim_naming_no_direction_is_inert(belief):
    belief.reset()
    snapshot = dict(belief.grid)
    for claim in (None, "STAY", ""):
        belief.update_from_hint(claim)
    assert belief.grid == snapshot


def test_mass_cannot_be_transported_through_a_wall(belief, board):
    """Belief pushed off the board would simply evaporate. It has to stay put."""
    belief.collapse((0, 3))
    belief.trust = 0.9
    belief.update_from_hint("N")  # row 0 is the top edge
    assert belief.probability((0, 3)) == pytest.approx(1.0)


def test_trust_rises_when_the_claim_matches_the_drift(belief):
    assert belief.score_claim("N", "N") is True
    assert belief.trust > TRUST_INITIAL


def test_trust_collapses_on_a_proven_liar(belief):
    """The book's worked example: claims north while the trail drifts south."""
    for _ in range(20):
        assert belief.score_claim("N", "S") is False
    assert belief.trust == pytest.approx(TRUST_FLOOR)
    assert belief.hints_contradicted == 20


def test_a_collapsed_trust_makes_further_claims_almost_inert(belief):
    for _ in range(20):
        belief.score_claim("N", "S")
    belief.collapse((3, 3))
    belief.update_from_hint("N")
    # Trust is at the floor, so almost nothing follows the claim.
    assert belief.probability((3, 3)) > 0.95


def test_trust_never_reaches_certainty_even_after_a_long_honest_streak(belief):
    """An opponent honest forty times may be setting up the forty-first."""
    for _ in range(40):
        belief.score_claim("E", "E")
    assert belief.trust <= TRUST_CEILING


def test_an_unreadable_turn_is_not_scored_as_honesty(belief):
    """No drift and no claim are both "nothing to go on", not "nothing wrong"."""
    assert belief.score_claim("N", None) is None
    assert belief.score_claim(None, "N") is None
    assert belief.score_claim("STAY", "N") is None
    assert belief.hints_seen == 0
    assert belief.trust == pytest.approx(TRUST_INITIAL)


def test_collapse_replaces_belief_with_certainty(belief):
    belief.collapse((2, 2))
    assert belief.grid == {(2, 2): 1.0}
    assert belief.most_likely() == (2, 2)


def test_queries_report_the_posterior(belief):
    belief.reset(known_start=(3, 3))
    belief.predict()
    assert len(belief.top(3)) == 3
    assert belief.expected_cell() is not None
    assert all("," in k for k in belief.as_dict())


def test_queries_are_safe_on_an_empty_map(board):
    empty = BeliefMap(board=board)
    empty.grid = {}  # a fresh map self-seeds, so empty it deliberately
    assert empty.most_likely() is None
    assert empty.expected_cell() is None
    assert empty.top() == []
