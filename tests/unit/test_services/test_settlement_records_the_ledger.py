"""A settled counted series must enter the rule-37 ledger.

`record_counted_game` existed, was tested, and had **no production caller**.
So `counted_games_played` answered 0 however many counted series we played,
and our step-0 declaration to every future opponent would have been false
under rules 37-38 -- silently, and in the direction that understates us.

anrbj666 found it on league issue #49 by reading the output of a check we had
posted to prove something else: our own printed standings showed `best2934: 0`
one comment after our prose declared 1. A test suite that exercises a function
nobody calls is a suite that proves the function works and nothing about the
program.

The ledger is written **before** the send and **regardless** of it: the series
happened, and a counted game whose mail failed is still a counted game we have
to declare.
"""

from __future__ import annotations

import json

import pytest

from p2pchase.reports.history import counted_games_played, counted_opponents
from p2pchase.services import settlement_report
from p2pchase.services.reporting_service import DeliveryReceipt


def _result(tmp_path, game_id="best2934-vs-imreeyal", sub_games=6):
    path = tmp_path / f"result_{game_id}.json"
    path.write_text(json.dumps({
        "game_id": game_id, "num_sub_games": sub_games,
        # The rows the length claims. The real builder always writes them, and
        # the one-series check refuses a result whose numbering is not 1..N.
        "sub_games": [{"sub_game_number": n} for n in range(1, sub_games + 1)],
        "final_result": {"winner_group": "best2934"}}), encoding="utf-8")
    return path


@pytest.fixture
def ledger(monkeypatch, tmp_path):
    """Point the TEAM-LEVEL ledger at the sandbox.

    This used to monkeypatch `settlement_report.artifacts_dir`, because the
    writer was handed a directory. It no longer is -- the ledger lives in
    `config/` and the writer resolves it itself -- so patching that name would
    sandbox nothing and every test here would append to the REAL repository
    ledger. Rule 52's dedupe is the only reason that was survivable when it
    happened on 2026-08-20; a test with a new opponent name would have written
    a false counted game into a committed file.
    """
    path = tmp_path / "counted_games.json"
    # Written empty rather than left absent: a missing ledger falls back to the
    # LEGACY `artifacts/counted_games.json`, so an absent sandbox file silently
    # reads the real repository's stale one and the assertions here would be
    # about our actual counted history instead of this test's.
    path.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("P2PCHASE_COUNTED_LEDGER", str(path))
    return path


@pytest.fixture
def sent(monkeypatch):
    calls: list[str] = []

    def _send(self, result, dry_run=False, to=""):
        calls.append(str(result.get("game_id")))
        return DeliveryReceipt(True, "x@y.z", "s", "a.json", "id1")

    monkeypatch.setattr("p2pchase.services.reporting_service.ReportingService.send_result",
                        _send)
    return calls


def test_a_settled_counted_series_enters_the_ledger(peer_config, tmp_path, ledger, sent):
    settlement_report.fire_if_settled(peer_config, "imreeyal", _result(tmp_path),
                                      counted=True)

    assert counted_opponents() == ["imreeyal"]
    assert counted_games_played() == 1


def test_a_friendly_never_enters_the_ledger(peer_config, tmp_path, ledger, sent):
    settlement_report.fire_if_settled(peer_config, "imreeyal", _result(tmp_path),
                                      counted=False)

    assert counted_opponents() == []


def test_an_incomplete_series_never_enters_the_ledger(peer_config, tmp_path, ledger,
                                                      sent):
    """Consistent-and-short must not count itself as a played game."""
    settlement_report.fire_if_settled(peer_config, "imreeyal",
                                      _result(tmp_path, sub_games=3), counted=True)

    assert counted_opponents() == []


def test_a_failed_send_still_records_the_game(peer_config, tmp_path, ledger,
                                              monkeypatch):
    """The series happened. Whether the mail left is a separate fact.

    Rule 37 asks what we played, not what we successfully posted -- and the
    first live firing of this path died on a missing dependency, so this is
    the realistic case rather than the exotic one.
    """
    monkeypatch.setattr(
        "p2pchase.services.reporting_service.ReportingService.send_result",
        lambda self, result, dry_run=False, to="": DeliveryReceipt(
            False, "x@y.z", "s", "a.json", reason="network down"))

    settlement_report.fire_if_settled(peer_config, "imreeyal", _result(tmp_path),
                                      counted=True)

    assert counted_opponents() == ["imreeyal"]


def test_rule_52_keeps_the_count_at_one_per_opponent(peer_config, tmp_path, ledger,
                                                     sent):
    """Re-running settlement must not inflate the declaration."""
    for _ in range(3):
        path = _result(tmp_path)
        settlement_report.receipt_path(tmp_path, "best2934-vs-imreeyal").unlink(
            missing_ok=True)
        settlement_report.fire_if_settled(peer_config, "imreeyal", path, counted=True)

    assert counted_opponents() == ["imreeyal"]
    assert counted_games_played() == 1


def test_two_different_opponents_both_count(peer_config, tmp_path, ledger, sent):
    """Two counted games against two teams is the pass threshold itself."""
    settlement_report.fire_if_settled(peer_config, "imreeyal", _result(tmp_path),
                                      counted=True)
    settlement_report.fire_if_settled(
        peer_config, "gal-roy1", _result(tmp_path, "best2934-vs-gal-roy1"),
        counted=True)

    assert counted_games_played() == 2
