"""The counted-games ledger is a fact about the team, not about a directory.

How many counted games we have played was once stored per repository. Rule 41
puts our cop and our thief in separate ones, so we kept two ledgers and they
drifted: the cop's read ``["imreeyal"]`` and the thief's read
``["imreeyal", "gal-roy1"]``. Every cop window we played declared 1 where the
truth was 2. anrbj666 found it on 2026-08-17; we never would have, because each
repository was internally consistent and only the pair was wrong.

The storage was moved to ``config/`` -- role-independent, committed, synced --
and that fixed it. What it did not fix was the call site:
:mod:`p2pchase.services.network_artifacts` still handed ``artifacts_dir()`` to
:func:`standings_block`, and an explicit directory bypasses the team-level
lookup entirely. So the ledger moved and the reader did not follow it, and every
result written afterwards declared 1 again -- from the stale file left behind at
the old location, which is still on disk precisely because nothing deletes it.

Found 2026-08-18 reading a friendly's result artifact, where
``games_played_including_this`` said ``best2934: 1`` against a ledger holding
two opponents. A friendly declares nothing to anyone, so it cost nothing; the
same field in a counted series is a false declaration under rule 38.
"""

from __future__ import annotations

import json
import pathlib

from p2pchase.reports.history import record_counted_game
from p2pchase.reports.standings import standings_block
from p2pchase.services import settlement_report


def _played(directory=None, **kw):
    block = standings_block("best2934", "anrbj666", kw.pop("counted", False),
                            kw.pop("opponent_games", 3), None, directory)
    return block["games_played_including_this"]["best2934"]


def test_the_default_ledger_is_the_team_one(tmp_path, monkeypatch):
    """No directory means the team ledger, wherever it lives."""
    team = tmp_path / "counted_games.json"
    team.write_text(json.dumps(["imreeyal", "gal-roy1"]), encoding="utf-8")
    monkeypatch.setenv("P2PCHASE_COUNTED_LEDGER", str(team))

    assert _played() == 2


def test_an_explicit_directory_reads_that_directory_and_nothing_else(tmp_path,
                                                                    monkeypatch):
    """Why the call site must not pass one.

    This is not a bug in :func:`counted_games_played` -- a caller that names a
    directory means it. It is a bug in *naming* one for a team-level fact, and
    this test exists so the two readings stay visibly different.
    """
    team = tmp_path / "counted_games.json"
    team.write_text(json.dumps(["imreeyal", "gal-roy1"]), encoding="utf-8")
    monkeypatch.setenv("P2PCHASE_COUNTED_LEDGER", str(team))

    stale = tmp_path / "artifacts"
    stale.mkdir()
    (stale / "counted_games.json").write_text(json.dumps(["imreeyal"]),
                                              encoding="utf-8")

    assert _played(directory=stale) == 1, "an explicit directory wins, as designed"
    assert _played() == 2, "and the team ledger is still the one we declare"


def test_a_counted_series_adds_itself_to_the_team_count(tmp_path, monkeypatch):
    """The number filed is the ledger plus this game, not the ledger alone."""
    team = tmp_path / "counted_games.json"
    team.write_text(json.dumps(["imreeyal", "gal-roy1"]), encoding="utf-8")
    monkeypatch.setenv("P2PCHASE_COUNTED_LEDGER", str(team))

    assert _played(counted=True) == 3


# --------------------------------------------------- and the WRITER, 2026-08-20
def test_a_settled_counted_series_is_recorded_where_the_reader_looks(tmp_path,
                                                                     monkeypatch):
    """The reader moved to `config/` and the WRITER was left behind too.

    `standings_block` was fixed on 2026-08-18. `record_counted_game` was not:
    `fire_if_settled` still handed it `artifacts_dir()`, so a settled counted
    series was appended to the per-repository ledger while every reader looked
    at the team-level one. After the anrbj666 counted series the two files held
    `["imreeyal", "gal-roy1"]` and `["imreeyal", "anrbj666"]` -- three games
    played and neither file knew it.

    Under-reporting a counted count is a false declaration under rule 38 in
    exactly the way over-reporting is.
    """
    ledger = tmp_path / "counted_games.json"
    ledger.write_text(json.dumps(["imreeyal", "gal-roy1"]), encoding="utf-8")
    monkeypatch.setenv("P2PCHASE_COUNTED_LEDGER", str(ledger))

    record_counted_game("anrbj666")

    assert json.loads(ledger.read_text(encoding="utf-8")) == [
        "imreeyal", "gal-roy1", "anrbj666"]


def test_the_writer_is_never_handed_a_directory_by_the_settlement_path():
    """Pins the call site itself, because that is what regressed twice."""
    source = pathlib.Path(settlement_report.__file__).read_text(encoding="utf-8")
    assert "record_counted_game(opponent)" in source
    assert "record_counted_game(opponent, artifacts_dir())" not in source
