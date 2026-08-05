"""The pheromone field: the one piece of unforgeable evidence (book ch4)."""

from __future__ import annotations

import pytest

from p2pchase.domain.board import BoardGeometry
from p2pchase.domain.crypto import digest_payload
from p2pchase.domain.smell import (
    BOOK_FIGURE_KERNEL,
    ScentMap,
    build_kernel,
    build_scent_map,
    gaussian_kernel,
    kernel_fingerprint,
    scent_model,
)


def test_the_book_kernel_is_symmetric_and_peaks_at_the_centre():
    assert len(BOOK_FIGURE_KERNEL) == 5
    assert BOOK_FIGURE_KERNEL[2][2] == 0.9
    for row in range(5):
        for col in range(5):
            assert BOOK_FIGURE_KERNEL[row][col] == BOOK_FIGURE_KERNEL[4 - row][col]
            assert BOOK_FIGURE_KERNEL[row][col] == BOOK_FIGURE_KERNEL[row][4 - col]


def test_the_gaussian_reproduces_the_book_figure_except_on_the_diagonal():
    """The two derivations agree everywhere but four cells, and by exactly 0.01.

    Pinning the discrepancy rather than waving at it is the point: the closed
    form gives 0.43 on the inner diagonal where the book's figure prints 0.42.
    If that ever becomes a different set of cells, or a larger gap, two teams
    reading the same figure would silently disagree about physical evidence.
    """
    derived = gaussian_kernel()
    differing = {
        (r, c): round(abs(derived[r][c] - BOOK_FIGURE_KERNEL[r][c]), 6)
        for r in range(5) for c in range(5)
        if abs(derived[r][c] - BOOK_FIGURE_KERNEL[r][c]) > 1e-9
    }
    assert set(differing) == {(1, 1), (1, 3), (3, 1), (3, 3)}
    assert set(differing.values()) == {0.01}


def test_the_kernel_choice_is_configurable(shared_config):
    book = build_kernel(shared_config)
    gauss = build_kernel({**shared_config,
                          "pheromones": {**shared_config["pheromones"],
                                         "pheromone_kernel": "gaussian"}})
    assert book == BOOK_FIGURE_KERNEL
    assert gauss != book  # they differ on the diagonal: 0.42 vs 0.43


def test_the_fingerprint_separates_the_two_kernels():
    """A silent kernel disagreement would corrupt a match; the handshake catches it."""
    a = kernel_fingerprint(BOOK_FIGURE_KERNEL, 0.10)
    b = kernel_fingerprint(gaussian_kernel(), 0.10)
    c = kernel_fingerprint(BOOK_FIGURE_KERNEL, 0.20)
    assert a != b
    assert a != c
    assert a == kernel_fingerprint(BOOK_FIGURE_KERNEL, 0.10)


#: The Appendix F model, locked with gal-roy1 (book ch4/p47). Both teams
#: reproduced this independently before either adopted the other's object.
AGREED_SCENT_FINGERPRINT = "e6a37eba68fc217534d08d0aba710515801fa218c24cd491d4e41fd96b3e8b2d"


def test_the_agreed_fingerprint_is_the_one_the_opponent_holds():
    """A literal, because this is a cross-team lock and not an internal detail.

    Every other test here asserts that *different* models hash *differently*,
    which stays true under any shape change and so cannot notice one. Our
    earlier object described identical physics and hashed to 57020f63 -- same
    formula, same kernel, same decay, two fields fewer -- and a lock nobody else
    computes the same number for locks nothing.
    """
    assert kernel_fingerprint(BOOK_FIGURE_KERNEL, 0.10) == AGREED_SCENT_FINGERPRINT


def test_the_published_model_is_exactly_what_gets_hashed():
    """Not a description of the digest, the object itself -- see ADR-020."""
    model = scent_model(BOOK_FIGURE_KERNEL, 0.10)
    assert digest_payload(model) == AGREED_SCENT_FINGERPRINT
    assert model["field_size"] == 5
    assert model["centre_intensity"] == 0.9
    assert model["worked_example"]["after_one_decay_turn"] == 0.81


def test_the_transmit_lag_is_not_folded_into_the_model():
    """It is a disclosure policy, not emission physics, and moving this digest
    would break a number both teams have already verified (ADR-022)."""
    assert not any("lag" in key for key in scent_model(BOOK_FIGURE_KERNEL, 0.10))


@pytest.fixture
def scent(shared_config):
    return build_scent_map(shared_config, BoardGeometry(7))


def test_emission_peaks_where_the_agent_stood(scent):
    scent.emit((3, 3))
    assert scent.intensity((3, 3)) == pytest.approx(0.9)
    assert scent.intensity((3, 4)) == pytest.approx(0.62)
    assert scent.intensity((3, 3)) > scent.intensity((1, 1))


def test_emission_is_clipped_at_the_board_edge(scent):
    scent.emit((0, 0))
    assert scent.intensity((0, 0)) == pytest.approx(0.9)
    assert scent.intensity((-1, 0)) == 0.0


def test_emission_accumulates_but_saturates_at_one(scent):
    for _ in range(10):
        scent.emit((3, 3))
    assert scent.intensity((3, 3)) <= 1.0


def test_decay_reduces_every_cell_by_the_agreed_rate(scent):
    scent.emit((3, 3))
    before = scent.intensity((3, 3))
    scent.decay_all()
    assert scent.intensity((3, 3)) == pytest.approx(before * 0.9, abs=1e-6)


def test_decay_eventually_clears_the_trail(scent):
    scent.emit((3, 3))
    for _ in range(400):
        scent.decay_all()
    assert scent.hottest() is None or scent.intensity((3, 3)) < 1e-3


def test_hottest_and_centre_of_mass_find_the_trail(scent):
    scent.emit((5, 5))
    cell, value = scent.hottest()
    assert cell == (5, 5)
    assert value == pytest.approx(0.9)
    assert scent.centre_of_mass() == (5, 5)


def test_an_empty_field_reports_nothing(shared_config):
    empty = build_scent_map(shared_config, BoardGeometry(7))
    assert empty.hottest() is None
    assert empty.centre_of_mass() is None


def test_serialisation_round_trips(scent):
    scent.emit((2, 4))
    other = ScentMap(geometry=scent.geometry, kernel=scent.kernel, decay=scent.decay)
    other.load(scent.as_dict())
    assert other.intensity((2, 4)) == pytest.approx(scent.intensity((2, 4)))


def test_merge_keeps_earlier_readings(scent):
    """Over the network a peer samples a few cells; a replace would erase the rest."""
    scent.load({"1,1": 0.5})
    scent.load({"2,2": 0.4}, merge=True)
    assert scent.intensity((1, 1)) == pytest.approx(0.5)
    assert scent.intensity((2, 2)) == pytest.approx(0.4)


def test_replace_is_the_default(scent):
    scent.load({"1,1": 0.5})
    scent.load({"2,2": 0.4})
    assert scent.intensity((1, 1)) == 0.0
