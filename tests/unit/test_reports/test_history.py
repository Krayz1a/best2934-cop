"""Declaring how many games we have played, truthfully (rules 37, 38, 52).

The bug these pin was found by building the first tool an opponent actually
calls. Their ``hello`` asks for ``counted_games_played``; our first
implementation derived it by counting result artifacts, and this repository's
``artifacts/`` contains finished results against ``rival999`` and ``test1234``
-- opponents invented during development. It answered "2" before we had played
anyone, which is precisely the false declaration rule 38 punishes, made
automatically and therefore invisibly.
"""

from __future__ import annotations

import json

import pytest

from p2pchase.reports.history import (
    counted_games_played,
    counted_opponents,
    discrepancies,
    ledger_path,
    record_counted_game,
)


@pytest.fixture
def artifacts(tmp_path):
    """An artifacts directory with two finished results and no ledger."""
    for opponent in ("rival999", "test1234"):
        (tmp_path / f"result_best2934-vs-{opponent}.json").write_text(
            json.dumps({"groups": sorted(["best2934", opponent])}), encoding="utf-8")
    return tmp_path


def test_played_games_are_not_counted_games(artifacts):
    """The whole point: two results on disk, zero games declared."""
    assert counted_games_played(artifacts) == 0


def test_a_warm_up_is_reported_but_is_not_a_violation(artifacts):
    """Rule 52 allows unlimited warm-ups, so a result without a ledger entry
    is the *expected* shape -- but it is still said out loud, because a counted
    game nobody recorded looks identical from here."""
    problems = discrepancies("best2934", artifacts)
    assert len(problems) == 2
    assert all("expected for a warm-up" in p for p in problems)


def test_declaring_a_game_with_nothing_to_show_for_it_is_a_violation(artifacts):
    """The direction that actually breaks rule 38: a claim with no evidence."""
    record_counted_game("ghost-team", artifacts)
    problems = discrepancies("best2934", artifacts)
    assert any("no result artifact to show for it" in p and "ghost-team" in p
               for p in problems)


def test_recording_the_same_opponent_twice_does_not_inflate_the_count(artifacts):
    """Rule 52: one counted game per pairing. A retry must not become a second."""
    record_counted_game("gal-roy1", artifacts)
    record_counted_game("gal-roy1", artifacts)
    assert counted_opponents(artifacts) == ["gal-roy1"]
    assert counted_games_played(artifacts) == 1


def test_a_corrupt_ledger_declares_nothing_rather_than_guessing(artifacts):
    """This is read inside a handshake. Refusing to say hello because a file
    will not parse would turn a bookkeeping fault into a forfeit -- but so
    would inventing a number, so it declares the one it can defend."""
    ledger_path(artifacts).write_text("{not json", encoding="utf-8")
    assert counted_games_played(artifacts) == 0


def test_a_missing_directory_is_not_an_error(tmp_path):
    assert discrepancies("best2934", tmp_path / "nope") == []
    assert counted_games_played(tmp_path / "nope") == 0
