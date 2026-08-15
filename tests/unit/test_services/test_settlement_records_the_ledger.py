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
    path.write_text(json.dumps({"game_id": game_id, "num_sub_games": sub_games,
                                "final_result": {"winner_group": "best2934"}}),
                    encoding="utf-8")
    return path


@pytest.fixture
def ledger(monkeypatch, tmp_path):
    """Point the ledger at the sandbox and capture sends."""
    root = tmp_path / "artifacts"
    root.mkdir()
    monkeypatch.setattr("p2pchase.services.settlement_report.artifacts_dir",
                        lambda counted=False: root)
    return root


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

    assert counted_opponents(ledger) == ["imreeyal"]
    assert counted_games_played(ledger) == 1


def test_a_friendly_never_enters_the_ledger(peer_config, tmp_path, ledger, sent):
    settlement_report.fire_if_settled(peer_config, "imreeyal", _result(tmp_path),
                                      counted=False)

    assert counted_opponents(ledger) == []


def test_an_incomplete_series_never_enters_the_ledger(peer_config, tmp_path, ledger,
                                                      sent):
    """Consistent-and-short must not count itself as a played game."""
    settlement_report.fire_if_settled(peer_config, "imreeyal",
                                      _result(tmp_path, sub_games=3), counted=True)

    assert counted_opponents(ledger) == []


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

    assert counted_opponents(ledger) == ["imreeyal"]


def test_rule_52_keeps_the_count_at_one_per_opponent(peer_config, tmp_path, ledger,
                                                     sent):
    """Re-running settlement must not inflate the declaration."""
    for _ in range(3):
        path = _result(tmp_path)
        settlement_report.receipt_path(tmp_path, "best2934-vs-imreeyal").unlink(
            missing_ok=True)
        settlement_report.fire_if_settled(peer_config, "imreeyal", path, counted=True)

    assert counted_opponents(ledger) == ["imreeyal"]
    assert counted_games_played(ledger) == 1


def test_two_different_opponents_both_count(peer_config, tmp_path, ledger, sent):
    """Two counted games against two teams is the pass threshold itself."""
    settlement_report.fire_if_settled(peer_config, "imreeyal", _result(tmp_path),
                                      counted=True)
    settlement_report.fire_if_settled(
        peer_config, "gal-roy1", _result(tmp_path, "best2934-vs-gal-roy1"),
        counted=True)

    assert counted_games_played(ledger) == 2
