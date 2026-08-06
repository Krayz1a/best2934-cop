"""The league's named scent models, checked against the kit's published fixtures.

The values below are transcribed from ``copthief-league-protocol`` at commit
``vectors/pheromone.json`` (status CORE) and ``vectors/locked_model.json``, read
as data with our own encoder. Their verifier was deliberately not executed --
running an opponent's script to prove our own conformance proves the script.

Transcribed rather than read from a checkout on purpose: a suite that needs
their repository present passes for a reason that has nothing to do with our
code, and fails on a machine that has never cloned it.
"""

from __future__ import annotations

import pytest

from p2pchase.domain import scent_models as sm
from p2pchase.domain.board import BoardGeometry
from p2pchase.domain.smell import ScentMap

#: sha256(canonical_json(doc)) for the two registered scent_model documents.
SUBTRACTIVE_SHA = "81ebee59640e80eae8ca9ee5f86abd26e7edf5cdbb27d15925cb6ee45ca6ddf4"
MULTIPLICATIVE_SHA = "934c220d5bf62acaa3297c6c9d723ea954c220260b02292ca17f6d5daef9f4d9"

#: The CORE emit case: a full 5x5 field at the centre of a 7x7 board.
EMIT_AT_CENTRE = {
    "1,1": 0.3, "1,2": 0.3, "1,3": 0.3, "1,4": 0.3, "1,5": 0.3,
    "2,1": 0.3, "2,2": 0.6, "2,3": 0.6, "2,4": 0.6, "2,5": 0.3,
    "3,1": 0.3, "3,2": 0.6, "3,3": 0.9, "3,4": 0.6, "3,5": 0.3,
    "4,1": 0.3, "4,2": 0.6, "4,3": 0.6, "4,4": 0.6, "4,5": 0.3,
    "5,1": 0.3, "5,2": 0.3, "5,3": 0.3, "5,4": 0.3, "5,5": 0.3,
}

#: The CORE emit case that clips: the same kernel at a corner.
EMIT_AT_CORNER = {
    "0,0": 0.9, "0,1": 0.6, "0,2": 0.3,
    "1,0": 0.6, "1,1": 0.6, "1,2": 0.3,
    "2,0": 0.3, "2,1": 0.3, "2,2": 0.3,
}


def _field(centre, board=7, model=sm.SUBTRACTIVE):
    scent = ScentMap(geometry=BoardGeometry(board), kernel=sm.chebyshev_kernel(),
                     decay=0.1, model=model)
    scent.emit(centre)
    return scent


def test_the_registered_documents_hash_to_the_leagues_published_values():
    """The whole mechanism is worthless unless two teams reach the same bytes.

    A bare hash over an ad-hoc dict is what this schema exists to replace: two
    correct implementations of one model serialise different field sets, declare
    different hashes, and refuse each other for no reason at all.
    """
    assert sm.locked_sha256(sm.SUBTRACTIVE) == SUBTRACTIVE_SHA
    assert sm.locked_sha256(sm.MULTIPLICATIVE) == MULTIPLICATIVE_SHA


def test_the_hash_is_a_test_of_the_physics_not_of_our_typing():
    """Both worked examples are *derived*, so wrong arithmetic cannot reach the
    published digest.

    Transcribing the examples would have made the test above pass for an
    implementation whose falloff or clamp was wrong -- it would be checking that
    we can copy 50 numbers out of a JSON file. Deriving them means the registered
    hash only reproduces if the model underneath it does.
    """
    example = sm.locked_doc(sm.SUBTRACTIVE)["example"]
    assert example["emit_field"] == EMIT_AT_CENTRE
    # 0.9 -> 0.8, 0.6 -> 0.5, 0.3 -> 0.2: a constant subtracted, not a factor.
    assert example["after_one_decay"]["3,3"] == 0.8
    assert example["after_one_decay"]["1,1"] == 0.2

    book = sm.locked_doc(sm.MULTIPLICATIVE)["example"]
    assert book["raw"] > 0.9 and book["clamped"] == 0.9, (
        "the book prints only max(0, .) yet declares tau in [0, 0.9]; without the "
        "upper clamp a saturated cell that decays and is deposited on again leaves "
        "the book's own stated range")


def test_the_chebyshev_falloff_makes_square_rings_not_radial_ones():
    """The visible difference between the two models, and the reason a pair has
    to pick one: at the same Euclidean distance the book's kernel reads 0.42 on
    the diagonal against 0.62 orthogonally, and this one reads 0.6 for both."""
    kernel = sm.chebyshev_kernel()
    assert kernel[2][2] == 0.9
    assert kernel[1][1] == kernel[1][2] == 0.6, "one ring out is one ring out"
    assert kernel[0][0] == kernel[0][2] == 0.3
    assert min(min(row) for row in kernel) > 0.0, (
        "a rim of 0.0 would be a 3x3 field wearing a 5x5 label")


def test_emission_reproduces_the_core_fixture():
    assert _field((3, 3)).as_dict() == EMIT_AT_CENTRE


def test_emission_at_a_corner_clips_to_the_board():
    """Two thirds of the kernel falls outside a 7x7 board and must not wrap,
    reflect, or land at a negative index."""
    assert _field((0, 0)).as_dict() == EMIT_AT_CORNER


def test_decay_subtracts_a_constant_and_stops_at_zero():
    scent = ScentMap(geometry=BoardGeometry(7), kernel=sm.chebyshev_kernel(),
                     decay=0.1, model=sm.SUBTRACTIVE)
    scent.load({"3,3": 0.9, "3,4": 0.6, "3,5": 0.3})
    scent.decay_all()
    assert scent.as_dict() == {"3,3": 0.8, "3,4": 0.5, "3,5": 0.2}


def test_a_cell_at_the_floor_reaches_exactly_zero_and_leaves_the_wire():
    """0.05 - 0.1 clamps to 0.0 rather than to -0.05 or to 1e-17.

    The zero is *kept in the map* and *dropped from the wire*: the field is
    transmitted, and only a positive value crosses. Under the book's model the
    same cell would decay towards zero forever and be pruned instead.
    """
    scent = ScentMap(geometry=BoardGeometry(7), kernel=sm.chebyshev_kernel(),
                     decay=0.1, model=sm.SUBTRACTIVE)
    scent.load({"1,1": 0.05})
    scent.decay_all()
    assert scent.grid[(1, 1)] == 0.0
    assert scent.as_dict() == {}


def test_emission_merges_by_max_so_a_stationary_agent_stops_climbing():
    """The book's model adds and caps; this one takes the larger. Standing still
    on a cell already at 0.9 must not push it anywhere."""
    scent = _field((3, 3))
    scent.emit((3, 3))
    assert scent.as_dict() == EMIT_AT_CENTRE


@pytest.mark.parametrize(("ours", "theirs", "refuse"), [
    (SUBTRACTIVE_SHA, SUBTRACTIVE_SHA, False),
    (SUBTRACTIVE_SHA, MULTIPLICATIVE_SHA, True),
    (SUBTRACTIVE_SHA, "", False),
    ("", MULTIPLICATIVE_SHA, False),
    ("", "", False),
])
def test_the_lock_refuses_only_when_both_peers_declare_and_disagree(ours, theirs, refuse):
    """The kit's five-row truth table, and the row that matters is the third.

    A lock that fail-fasts on a *missing* declaration cannot start a game
    against a peer that declares nothing -- which is most of the league. That is
    a self-inflicted forfeit under rule 6 dressed up as a safeguard.
    """
    assert sm.lock_refuses(ours, theirs) is refuse


def test_an_unregistered_model_raises_rather_than_falling_back():
    """A typo that silently resolved to the default would put two peers on
    different physics while both believed they had locked the same one -- which
    plays, and then makes the audits disagree."""
    with pytest.raises(ValueError, match="unregistered scent model"):
        sm.locked_doc("gaussian_v9")


def test_a_session_runs_the_physics_it_declared(peer_config):
    """The loop this closes: a hash of a document says nothing about the code
    under it.

    Declaring ``subtractive_chebyshev_v1`` at the handshake and then emitting
    the book's kernel is a false declaration that *passes* -- the opponent
    checks the hash, sees exactly what they expected, and the mismatch surfaces
    much later as a trail that does not behave. So the pairing has to reach the
    maps, not only the greeting.
    """
    from p2pchase.runtime.peer_session import PeerSession

    peer_config.setup["opponents"] = {"imreeyal": {"scent_model": sm.SUBTRACTIVE}}
    session = PeerSession(peer_config, "police", "imreeyal-vs-test1234", sub_game=1, seed=1)

    assert session.opponent == "imreeyal", "the opponent is readable off the game id"
    assert session.state.my_scent.model == sm.SUBTRACTIVE
    assert session.state.my_scent.kernel[1][1] == 0.6, "Chebyshev rings, not the book's 0.42"


def test_an_unknown_opponent_falls_back_to_the_book_rather_than_to_a_guess(peer_config):
    """Every team in the league holds the book; almost none hold our pairings."""
    from p2pchase.runtime.peer_session import PeerSession

    session = PeerSession(peer_config, "police", "someone-new-vs-test1234", sub_game=1, seed=1)
    assert session.state.my_scent.model == sm.MULTIPLICATIVE
