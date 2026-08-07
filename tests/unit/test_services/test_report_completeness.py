"""A report shorter than the signed series must never leave the building.

imreeyal reported losing a series to this exact shape on 6 August: a driver
that stopped correctly at sub-game 3 and then mailed a perfectly consistent
two-game "series tie" for a six-game match. Nothing inside such an artifact
contradicts itself, so no amount of internal validation catches it -- only a
check against the *signed* length does.
"""

from p2pchase.services.reporting_service import ReportingService


def _result(played: int) -> dict:
    """A result artifact that is internally consistent at any length."""
    return {"game_id": "best2934-vs-imreeyal", "game_uid": "uid-1",
            "num_sub_games": played, "final_result": {"winner_group": None},
            "mutual_agreement": {"sha256": "abc"}}


def test_a_short_series_is_refused_before_it_is_sent(peer_config, monkeypatch):
    """Three sub-games against a signed six is a refusal, not a report."""
    monkeypatch.setitem(peer_config.email, "enabled", True)
    service = ReportingService(peer_config, gatekeeper=_ExplodingGate())

    receipt = service.send_result(_result(3))

    assert not receipt.sent, "an incomplete report was delivered"
    assert "3 sub-game(s)" in receipt.reason and "6" in receipt.reason, receipt.reason


def test_a_complete_series_still_goes_out(peer_config):
    """The guard must not become a blanket refusal to report anything."""
    service = ReportingService(peer_config, gatekeeper=_ExplodingGate())
    assert service.incompleteness(_result(peer_config.num_sub_games)) == ""


def test_an_over_long_series_is_refused_too(peer_config):
    """Seven sub-games is as wrong as five, and likelier to be a double-count."""
    assert service_reason(peer_config, 7)


def test_a_missing_count_is_not_read_as_agreement(peer_config):
    """An artifact with no count at all reads as zero, never as complete."""
    assert service_reason(peer_config, None)


def service_reason(config, played) -> str:
    payload = _result(0)
    if played is None:
        payload.pop("num_sub_games")
    else:
        payload["num_sub_games"] = played
    return ReportingService(config, gatekeeper=_ExplodingGate()).incompleteness(payload)


class _ExplodingGate:
    """Any real send during these tests is itself the failure."""

    def execute(self, *args, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("an incomplete report reached the Gatekeeper")
