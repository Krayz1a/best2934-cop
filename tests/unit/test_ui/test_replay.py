"""The replay verifier: the gate a log has to pass (book ch7.4-7.5, rules 19-20)."""

from __future__ import annotations

import json

import pytest

from p2pchase.domain.crypto import commit
from p2pchase.ui.replay import (
    load_log,
    reconstruct_boards,
    render_text,
    replay_file,
    verify_log,
)


def make_log(steps: int = 4) -> dict:
    records = [
        commit({"step": n, "role": "police", "move": "E", "hint": f"hint {n}",
                "intent": "truth"}).audit_view()
        for n in range(1, steps + 1)
    ]
    return {
        "game_id": "a-vs-b",
        "summary": {"sub_game_number": 1, "role": "police", "result": "survival"},
        "records": records,
    }


def test_an_intact_log_verifies():
    result = verify_log(make_log())
    assert result.passed
    assert result.verified_steps == 4
    assert result.banner() == "Verified OK — 4/4 steps"
    assert all(v.badge == "OK" for v in result.verdicts)


def test_altering_one_byte_is_provable():
    """No statistical judgement here -- the cryptography decides, not a person."""
    log = make_log()
    log["records"][1]["payload"]["move"] = "W"
    result = verify_log(log)
    assert not result.passed
    assert result.failed_steps == [2]
    assert "INTEGRITY FAILURE" in result.banner()
    assert "technical loss, score 0" in result.banner()


def test_swapping_a_nonce_is_provable():
    log = make_log()
    log["records"][0]["nonce"] = log["records"][1]["nonce"]
    assert not verify_log(log).passed


def test_a_record_with_no_payload_fails_rather_than_being_skipped():
    log = make_log(1)
    del log["records"][0]["payload"]
    result = verify_log(log)
    assert not result.passed
    assert "no payload" in result.verdicts[0].reason


def test_a_record_with_no_nonce_fails():
    log = make_log(1)
    del log["records"][0]["nonce"]
    result = verify_log(log)
    assert not result.passed
    assert "nonce or commitment missing" in result.verdicts[0].reason


def test_an_empty_log_is_vacuously_clean():
    result = verify_log({"records": []})
    assert result.passed
    assert result.banner() == "Verified OK — 0/0 steps"


def test_the_board_is_reconstructed_from_declared_barriers():
    log = make_log(1)
    log["records"].append(
        commit({"step": 2, "role": "police", "move": "STAY", "hint": "wall",
                "barrier": [2, 2]}).audit_view())
    boards = list(reconstruct_boards(log))
    assert (2, 2) in boards[-1][1].barriers


def test_the_text_report_ends_with_the_verdict():
    text = render_text(verify_log(make_log()))
    assert text.strip().endswith("Verified OK — 4/4 steps")
    assert "Replay — game a-vs-b" in text


def test_the_text_report_can_be_truncated():
    text = render_text(verify_log(make_log(20)), limit=3)
    assert "17 more steps" in text


def test_a_long_hint_is_elided_rather_than_wrapping():
    log = make_log(1)
    log["records"][0]["payload"]["hint"] = "x" * 90
    assert "…" in render_text(verify_log(log))


def test_a_log_file_round_trips(tmp_path, capsys):
    path = tmp_path / "log.json"
    path.write_text(json.dumps(make_log()), encoding="utf-8")
    assert load_log(path)["game_id"] == "a-vs-b"
    result = replay_file(path)
    assert result.passed
    assert "Verified OK" in capsys.readouterr().out


def test_a_missing_log_file_is_a_clear_failure(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_log(tmp_path / "nope.json")
