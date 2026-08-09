"""Capture is off by default, writes outside the repo, and never raises.

Added because a diagnosis stalled for want of evidence: six audits failed
against imreeyal and their disclosed chain existed only in memory. The tests
that matter here are the negative ones -- a diagnostic that can abort a live
sub-game is worse than no diagnostic, and one that writes another team's wire
traffic into a public repository is worse still.
"""

from __future__ import annotations

import json

from p2pchase.runtime import opponent_capture

TURN = {"step": 3, "sender": "thief", "smell_grid": {"2,3": 0.9}, "commit": "a" * 64}


def test_off_by_default(monkeypatch, tmp_path):
    monkeypatch.delenv(opponent_capture.CAPTURE_DIR_ENV, raising=False)
    opponent_capture.note_turn(3, TURN)
    assert list(tmp_path.iterdir()) == []


def test_capture_dir_is_none_when_unset(monkeypatch):
    monkeypatch.delenv(opponent_capture.CAPTURE_DIR_ENV, raising=False)
    assert opponent_capture.capture_dir() is None


def test_blank_is_treated_as_unset(monkeypatch):
    monkeypatch.setenv(opponent_capture.CAPTURE_DIR_ENV, "   ")
    assert opponent_capture.capture_dir() is None


def test_a_turn_is_written_verbatim(monkeypatch, tmp_path):
    monkeypatch.setenv(opponent_capture.CAPTURE_DIR_ENV, str(tmp_path))
    opponent_capture.note_turn(3, TURN)
    entry = json.loads((tmp_path / "turns.jsonl").read_text().strip())
    assert entry == {"step": 3, "message": TURN}


def test_turns_append_rather_than_overwrite(monkeypatch, tmp_path):
    monkeypatch.setenv(opponent_capture.CAPTURE_DIR_ENV, str(tmp_path))
    for step in (1, 2, 3):
        opponent_capture.note_turn(step, dict(TURN, step=step))
    lines = (tmp_path / "turns.jsonl").read_text().strip().splitlines()
    assert [json.loads(line)["step"] for line in lines] == [1, 2, 3]


def test_an_audit_chain_is_kept(monkeypatch, tmp_path):
    monkeypatch.setenv(opponent_capture.CAPTURE_DIR_ENV, str(tmp_path))
    opponent_capture.note_audit({"records": [{"payload": {}}], "verdict": {"passed": False}})
    assert "records" in json.loads((tmp_path / "audits.jsonl").read_text().strip())["payload"]


def test_an_unwritable_directory_does_not_raise(monkeypatch, tmp_path):
    """Rule 6 charges both teams for a stall. A diagnostic must never cause one."""
    blocker = tmp_path / "afile"
    blocker.write_text("not a directory")
    monkeypatch.setenv(opponent_capture.CAPTURE_DIR_ENV, str(blocker / "under"))
    opponent_capture.note_turn(3, TURN)  # must not raise


def test_unserialisable_content_does_not_raise(monkeypatch, tmp_path):
    monkeypatch.setenv(opponent_capture.CAPTURE_DIR_ENV, str(tmp_path))
    opponent_capture.note_turn(3, {"step": 3, "bad": {1, 2}})  # a set is not JSON


def test_a_missing_smell_grid_is_logged_as_absent(monkeypatch, tmp_path, caplog):
    """The line that answers the current question, so it must survive refactors."""
    monkeypatch.setenv(opponent_capture.CAPTURE_DIR_ENV, str(tmp_path))
    with caplog.at_level("INFO"):
        opponent_capture.note_turn(4, {"step": 4})
    assert "entries=-1" in caplog.text


def test_an_empty_smell_grid_is_logged_as_zero(monkeypatch, tmp_path, caplog):
    monkeypatch.setenv(opponent_capture.CAPTURE_DIR_ENV, str(tmp_path))
    with caplog.at_level("INFO"):
        opponent_capture.note_turn(4, {"step": 4, "smell_grid": {}})
    assert "entries=0" in caplog.text
