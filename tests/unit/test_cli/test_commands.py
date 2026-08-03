"""The CLI, tested as a shell contract rather than as prose.

Two things matter here and neither is the printed text. First, the exit code:
``p2pchase verify`` is meant to be usable in a CI gate, so a failed audit must
exit non-zero and a passing one must exit zero. Second, the layering
(guidelines §4.1) -- every command goes through the SDK, so a command that
still works when the SDK is stubbed out would be one that had grown its own
logic.
"""

from __future__ import annotations

import json
from argparse import Namespace

import pytest

from p2pchase.cli import commands
from p2pchase.cli.commands import EXIT_CONFIG, EXIT_FAILED, EXIT_OK


@pytest.fixture
def args(config_dir, tmp_path) -> Namespace:
    return Namespace(role="police", config_dir=str(config_dir), output=str(tmp_path),
                     opponent="rival999", sub_games=1, seed=1, limit=5,
                     log=None, logs=[], result=None, live=False, port=0)


@pytest.fixture
def played(args, tmp_path):
    """A real series on disk, so the verify/audit commands have logs to read."""
    assert commands.local_match(args) == EXIT_OK
    return sorted(tmp_path.glob("log_*.json"))


def test_describe_prints_parseable_json(args, capsys):
    assert commands.describe(args) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["role"] == "police"
    assert payload["config_sha256"]


def test_check_config_accepts_a_legal_configuration(args, capsys):
    assert commands.check_config(args) == EXIT_OK
    assert "Configuration is legal" in capsys.readouterr().out


def test_check_config_refuses_an_illegal_one(args, config_dir, capsys):
    """A PERMANENT Appendix F value is not negotiable, so this must fail loudly.

    The decay rate is one of them: two peers running different decay would build
    incompatible scent fields while both believing the match was fair.
    """
    game = json.loads((config_dir / "game.json").read_text(encoding="utf-8"))
    game["pheromones"]["pheromone_decay"] = 0.5
    (config_dir / "game.json").write_text(json.dumps(game), encoding="utf-8")

    assert commands.check_config(args) == EXIT_CONFIG
    assert "ILLEGAL CONFIGURATION" in capsys.readouterr().out


def test_handshake_publishes_the_fingerprints_an_opponent_checks(args, capsys):
    assert commands.handshake(args) == EXIT_OK
    payload = json.loads(capsys.readouterr().out)
    assert payload["config_sha256"]
    assert payload["scent_fingerprint"]


def test_local_match_writes_artifacts_and_names_them(args, tmp_path, capsys):
    assert commands.local_match(args) == EXIT_OK
    out = capsys.readouterr().out
    assert "artifacts written:" in out
    assert list(tmp_path.glob("result_*.json"))


def test_verify_exits_zero_on_an_intact_log(args, played, capsys):
    args.log = str(played[0])
    assert commands.verify(args) == EXIT_OK
    assert "Verified OK" in capsys.readouterr().out


def test_verify_exits_non_zero_on_a_tampered_log(args, played, capsys):
    """The exit code is the part a CI gate reads, so it is asserted directly."""
    payload = json.loads(played[0].read_text(encoding="utf-8"))
    payload["records"][1]["payload"]["move"] = "STAY"
    played[0].write_text(json.dumps(payload), encoding="utf-8")

    args.log = str(played[0])
    assert commands.verify(args) == EXIT_FAILED
    assert "INTEGRITY FAILURE" in capsys.readouterr().out


def test_audit_reports_every_log_it_was_given(args, played, capsys):
    args.logs = [str(p) for p in played]
    assert commands.audit(args) == EXIT_OK
    assert "ALL LOGS VERIFIED" in capsys.readouterr().out


def test_audit_says_so_when_there_is_nothing_to_audit(args, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("p2pchase.cli.commands.artifacts_dir", lambda: tmp_path / "empty")
    (tmp_path / "empty").mkdir()
    args.logs = []
    assert commands.audit(args) == EXIT_CONFIG
    assert "no log files given" in capsys.readouterr().out


def test_send_report_defaults_to_a_dry_run(args, tmp_path, played, capsys):
    """Nothing may leave the machine unless a human passed --live."""
    result = next(tmp_path.glob("result_*.json"))
    args.result = str(result)
    assert commands.send_report(args) == EXIT_OK
    out = capsys.readouterr().out
    assert "Dry run: nothing was sent" in out
    assert json.loads(out.split("\n\nDry run")[0])["sent"] is False


def test_gate_status_reports_the_queue(args, capsys):
    assert commands.gate_status(args) == EXIT_OK
    assert "depth" in capsys.readouterr().out


def test_authorize_gmail_reports_a_setup_problem_instead_of_raising(args, monkeypatch, capsys):
    from p2pchase.infra.gmail_sender import GmailNotConfiguredError

    def _refuse(port: int = 0):
        raise GmailNotConfiguredError("no OAuth client file")

    monkeypatch.setattr("p2pchase.infra.gmail_sender.authorize", _refuse)
    assert commands.authorize_gmail(args) == EXIT_CONFIG
    assert "Gmail is not set up" in capsys.readouterr().out
