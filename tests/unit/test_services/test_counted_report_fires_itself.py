"""Rule 32: the agent files the counted report, not the operator.

Our reporting service claimed this in its own docstring from the day it was
written -- *"the agent -- not a human -- e-mails the result to the lecturer"* --
and the only caller of ``send_result`` was a CLI command a person runs by hand
with ``--live``. Every flight this week was operator-armed.

imreeyal made it the one precondition they needed in writing before a counted
series: an operator-armed send is a single point of failure, and rule 35 prices
a missing report at *both* teams' scores.

An automatic mailer is also the most dangerous object in this codebase -- a bug
in the match loop becomes a bug that sends mail in a loop -- so most of these
tests are about when it must stay silent.
"""

from __future__ import annotations

import json

import pytest

from p2pchase.services import settlement_report
from p2pchase.services.reporting_service import DeliveryReceipt


def _result(tmp_path, sub_games=6, game_id="best2934-vs-imreeyal"):
    path = tmp_path / f"result_{game_id}.json"
    path.write_text(json.dumps({"game_id": game_id, "num_sub_games": sub_games,
                                "final_result": {"winner_group": "best2934"}}),
                    encoding="utf-8")
    return path


@pytest.fixture
def sent(monkeypatch):
    """Capture sends instead of performing them."""
    calls: list[dict] = []

    def _send(self, result, dry_run=False, to=""):
        calls.append({"game_id": result.get("game_id"), "to": to})
        return DeliveryReceipt(True, self.config.email["recipient"], "s", "a.json", "id1")

    monkeypatch.setattr("p2pchase.services.reporting_service.ReportingService.send_result",
                        _send)
    return calls


def test_a_settled_counted_series_fires_without_a_human(peer_config, tmp_path, sent):
    receipt = settlement_report.fire_if_settled(
        peer_config, "imreeyal", _result(tmp_path), counted=True)

    assert receipt is not None and receipt.sent
    assert len(sent) == 1


def test_a_friendly_never_mails_the_lecturer(peer_config, tmp_path, sent):
    """The dangerous direction. A friendly reaching the marker is not recoverable."""
    assert settlement_report.fire_if_settled(
        peer_config, "imreeyal", _result(tmp_path), counted=False) is None
    assert sent == []


def test_an_incomplete_series_is_held_rather_than_filed(peer_config, tmp_path, sent):
    """Consistent-and-short is the shape no check inside the artifact can catch.

    imreeyal lost a series to exactly this: a driver that stopped at sub-game 3
    and mailed a perfectly consistent two-game "series tie" for a six-game
    match.
    """
    assert settlement_report.fire_if_settled(
        peer_config, "imreeyal", _result(tmp_path, sub_games=3), counted=True) is None
    assert sent == []


def test_it_fires_exactly_once_however_often_the_result_is_refreshed(peer_config,
                                                                    tmp_path, sent):
    """`refresh_result` runs after EVERY sub-game, and re-runs are routine."""
    path = _result(tmp_path)
    for _ in range(4):
        settlement_report.fire_if_settled(peer_config, "imreeyal", path, counted=True)

    assert len(sent) == 1


def test_the_receipt_is_the_sentinel_and_records_what_happened(peer_config, tmp_path,
                                                               sent):
    settlement_report.fire_if_settled(peer_config, "imreeyal", _result(tmp_path),
                                      counted=True)

    receipt = settlement_report.receipt_path(tmp_path, "best2934-vs-imreeyal")
    assert receipt.exists()
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["game_id"] == "best2934-vs-imreeyal"
    assert payload["opponent"] == "imreeyal"
    assert payload["sent"] is True


def test_a_failed_send_is_recorded_and_not_retried(peer_config, tmp_path, monkeypatch):
    """A mailer that retries itself on every refresh is how an account is suspended.

    The failure must be loud on disk and dealt with by a person, not silently
    hammered into a rate limit at the one moment it matters.
    """
    attempts: list[int] = []

    def _fail(self, result, dry_run=False, to=""):
        attempts.append(1)
        return DeliveryReceipt(False, "x@y.z", "s", "a.json", reason="network down")

    monkeypatch.setattr("p2pchase.services.reporting_service.ReportingService.send_result",
                        _fail)
    path = _result(tmp_path)
    for _ in range(3):
        settlement_report.fire_if_settled(peer_config, "imreeyal", path, counted=True)

    assert len(attempts) == 1
    payload = json.loads(
        settlement_report.receipt_path(tmp_path, "best2934-vs-imreeyal").read_text())
    assert payload["sent"] is False
    assert "network down" in payload["reason"]


def test_it_never_redirects_a_counted_report(peer_config, tmp_path, sent):
    """`to` stays empty, so the recipient is the one Appendix F fixes."""
    settlement_report.fire_if_settled(peer_config, "imreeyal", _result(tmp_path),
                                      counted=True)

    assert sent[0]["to"] == ""


def test_an_unreadable_result_does_not_take_down_the_match(peer_config, tmp_path, sent):
    """The artifacts are still the evidence; a mail failure must not lose them."""
    broken = tmp_path / "result_best2934-vs-imreeyal.json"
    broken.write_text("{not json", encoding="utf-8")

    assert settlement_report.fire_if_settled(peer_config, "imreeyal", broken,
                                             counted=True) is None
    assert sent == []


def test_recording_a_sub_game_fires_it_through_the_real_service(peer_config, tmp_path,
                                                                sent, monkeypatch):
    """The wiring, since the defect was that nothing called the sender at all."""
    from p2pchase.services.network_artifacts import NetworkArtifactService

    fired: list[bool] = []
    monkeypatch.setattr(
        "p2pchase.services.network_artifacts.settlement_report.fire_if_settled",
        lambda config, opponent, path, counted: fired.append(counted))
    monkeypatch.setattr(
        "p2pchase.services.network_artifacts.NetworkArtifactService.refresh_result",
        lambda self, game_id, game_uid, opponent: tmp_path / "result.json")
    monkeypatch.setattr(
        "p2pchase.services.network_artifacts.NetworkArtifactService.ensure_declaration",
        lambda self, names, game_id, handshake, started: ("uid", tmp_path / "d.json"))

    class _Outcome:
        outcome, records, opponent_audit, steps = "capture", [], {}, 15

    service = NetworkArtifactService(peer_config, tmp_path, counted=True)
    service.record_sub_game("best2934-vs-imreeyal", 6, "police", "imreeyal",
                            _Outcome(), "s", "e", 0)

    assert fired == [True]
