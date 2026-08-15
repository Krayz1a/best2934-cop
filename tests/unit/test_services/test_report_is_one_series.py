"""A report must be one series, not every log we ever wrote to that opponent.

``series_logs`` globs every ``log_<game_id>_g*.json`` on disk, and both
``game_id`` and ``game_uid`` are **pairing** identifiers -- byte-identical
across every series played against one opponent. Nothing in the artifacts
carries a series boundary, so a second series assembles on top of the first.

Measured 2026-08-16 against gal-roy1, before anything counted was played: the
result carried eleven rows spanning 17:20 to 21:00, numbered 0..11, no 5, and a
duplicate ``started_at`` on 6 and 7.

The count check caught that one only because eleven is not six. The case it
cannot catch is the one that matters: three stale logs plus three fresh ones
total exactly six, contradict nothing inside the artifact, and get filed --
and rule 35 charges *both* teams when the two reports disagree.
"""

from __future__ import annotations

import pytest


def _result(numbers, count=None):
    return {"num_sub_games": len(numbers) if count is None else count,
            "sub_games": [{"sub_game_number": n} for n in numbers]}


@pytest.fixture
def service(peer_config, tmp_path):
    from p2pchase.services.reporting_service import ReportingService

    peer_config.setup["num_sub_games"] = 6
    return ReportingService(peer_config)


def test_a_clean_series_is_accepted(service):
    assert service.incompleteness(_result([1, 2, 3, 4, 5, 6])) == ""


def test_order_on_disk_does_not_matter(service):
    """Logs arrive from two repositories; sorted() is the caller's business."""
    assert service.incompleteness(_result([4, 6, 2, 1, 5, 3])) == ""


def test_the_eleven_row_mixture_is_refused(service):
    """The gal-roy1 artifact as it actually stood on 2026-08-16."""
    reason = service.incompleteness(_result([0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 11]))

    assert "incomplete" in reason
    assert "11" in reason


def test_a_mixture_that_totals_six_is_refused(service):
    """THE case the count check passes: three stale logs plus three fresh.

    Six rows against a signed six. Every self-check inside the artifact holds.
    Only the numbering shows that this is two series stitched together.
    """
    reason = service.incompleteness(_result([1, 2, 3, 1, 2, 3]))

    assert "not one series" in reason
    assert "archive" in reason


def test_a_duplicated_row_is_refused(service):
    assert "not one series" in service.incompleteness(_result([1, 2, 3, 4, 5, 5]))


def test_a_zero_numbered_row_is_refused(service):
    """A row numbered 0 is what an undeclared sub-game settles as."""
    assert "not one series" in service.incompleteness(_result([0, 1, 2, 3, 4, 5]))


def test_the_refusal_names_the_numbers_it_saw(service):
    """An operator at settlement needs the shape, not the verdict."""
    reason = service.incompleteness(_result([1, 2, 3, 1, 2, 3]))

    assert "[1, 1, 2, 2, 3, 3]" in reason


def test_the_count_check_still_fires_first(service):
    """Short series keep their own message; it names the missing games."""
    assert "incomplete" in service.incompleteness(_result([1, 2, 3]))
