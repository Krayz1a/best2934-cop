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

from p2pchase.reports import history
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


# ------------------------------------------------- one ledger, not one per repo
#
# The drift that caused this: rule 41 puts our cop and our thief in separate
# repositories, the ledger lived in each one's `artifacts/`, and the two
# disagreed. Cop read ["imreeyal"], thief read ["imreeyal", "gal-roy1"], so
# every cop window declared 1 where the truth was 2 (rule 37, sanctioned by
# rule 38). Neither repository could detect it: each was internally consistent
# and only the PAIR was wrong. anrbj666 found it on 2026-08-17.

def test_the_ledger_is_not_kept_in_the_artifacts_tree():
    """THE regression. `artifacts/` is per-repository and never synced.

    :mod:`tools.sync_thief` must never copy that directory -- the two halves of
    a six-sub-game series live there and mirroring one over the other destroys
    half the evidence -- so anything stored in it drifts between the repos by
    construction. A team-level declaration cannot live there.
    """
    from p2pchase.shared.paths import artifacts_dir
    assert artifacts_dir() not in history.ledger_path().parents


def test_the_ledger_lives_in_the_synced_config_tree():
    from p2pchase.shared.paths import config_dir
    assert history.ledger_path().parent == config_dir()


def test_an_operator_can_point_both_repos_at_one_file(tmp_path, monkeypatch):
    shared = tmp_path / "counted_games.json"
    monkeypatch.setenv("P2PCHASE_COUNTED_LEDGER", str(shared))
    assert history.ledger_path() == shared


def test_the_legacy_ledger_is_still_read_while_it_exists(tmp_path, monkeypatch):
    """An upgrade must never silently drop the count back to zero.

    A ledger that reads 0 declares 0, and rule 38 sanctions a false declaration
    in whichever direction it is wrong.
    """
    legacy = tmp_path / "artifacts"
    legacy.mkdir()
    (legacy / history.LEDGER_NAME).write_text('["imreeyal", "gal-roy1"]', encoding="utf-8")
    monkeypatch.setenv("P2PCHASE_COUNTED_LEDGER", str(tmp_path / "absent.json"))
    monkeypatch.setattr(history, "artifacts_dir", lambda *a, **k: legacy)
    assert history.counted_opponents() == ["imreeyal", "gal-roy1"]
