"""``.env`` reaches the process, and never overrides a real export.

The bug these cover was silent in the worst way: ``authorize-gmail`` reported
"no OAuth client file at credentials.json" while the operator was looking at
the absolute path they had written into ``.env`` an hour earlier. Nothing in
the codebase read the file -- only ``tools/endpoint.py`` did, for the peer it
launched, so a served match was signed and a CLI invocation was not.
"""

from __future__ import annotations

import pytest

from p2pchase.shared import dotenv

SAMPLE = """
# a comment
P2PCHASE_GMAIL_SENDER=someone@example.com

P2PCHASE_GMAIL_CREDENTIALS=/outside/the/repo/credentials.json
malformed line without an equals sign
"""


def test_parse_keeps_pairs_and_drops_noise():
    values = dotenv.parse(SAMPLE)
    assert values == {
        "P2PCHASE_GMAIL_SENDER": "someone@example.com",
        "P2PCHASE_GMAIL_CREDENTIALS": "/outside/the/repo/credentials.json",
    }


@pytest.mark.parametrize("line, expected", [
    ('K="quoted"', "quoted"),
    ("K='quoted'", "quoted"),
    ("K=  spaced  ", "spaced"),
    ("K=", ""),
    ("K=a=b", "a=b"),          # only the first ``=`` separates
])
def test_parse_value_forms(line, expected):
    assert dotenv.parse(line)["K"] == expected


def test_load_fills_absent_names(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("P2PCHASE_TEST_ONLY=from-file\n", encoding="utf-8")
    monkeypatch.delenv("P2PCHASE_TEST_ONLY", raising=False)

    assert dotenv.load(tmp_path) == ["P2PCHASE_TEST_ONLY"]

    import os
    assert os.environ["P2PCHASE_TEST_ONLY"] == "from-file"


def test_a_real_export_wins_over_a_stale_file(tmp_path, monkeypatch):
    """An operator who exports by hand is debugging. Do not fight them."""
    (tmp_path / ".env").write_text("P2PCHASE_TEST_ONLY=from-file\n", encoding="utf-8")
    monkeypatch.setenv("P2PCHASE_TEST_ONLY", "from-shell")

    assert dotenv.load(tmp_path) == []
    assert dotenv.environment(tmp_path)["P2PCHASE_TEST_ONLY"] == "from-shell"


def test_missing_file_is_not_an_error(tmp_path, monkeypatch):
    """Cloning the repo and running a local match must not require a ``.env``."""
    monkeypatch.setenv("PATH", "/usr/bin")
    assert dotenv.load(tmp_path) == []
    assert dotenv.environment(tmp_path)["PATH"] == "/usr/bin"


def test_environment_does_not_mutate_the_process(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("P2PCHASE_TEST_ONLY=from-file\n", encoding="utf-8")
    monkeypatch.delenv("P2PCHASE_TEST_ONLY", raising=False)

    merged = dotenv.environment(tmp_path)

    import os
    assert merged["P2PCHASE_TEST_ONLY"] == "from-file"
    assert "P2PCHASE_TEST_ONLY" not in os.environ


def test_load_reports_names_but_the_caller_gets_no_values(tmp_path, monkeypatch):
    """The return value is logged. Secrets must not be in it (rules 39-40)."""
    (tmp_path / ".env").write_text("P2PCHASE_SIGNING_SECRET=hunter2\n", encoding="utf-8")
    monkeypatch.delenv("P2PCHASE_SIGNING_SECRET", raising=False)

    reported = dotenv.load(tmp_path)

    assert reported == ["P2PCHASE_SIGNING_SECRET"]
    assert "hunter2" not in "".join(reported)
