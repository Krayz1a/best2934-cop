"""The three rate-control guards (book ch9.3.1)."""

from __future__ import annotations

import pytest

from p2pchase.infra.rate_limiter import DosDetector, QuotaManager, TokenBucket


def test_a_bucket_starts_full_so_the_first_burst_is_not_punished():
    bucket = TokenBucket(capacity=3, refill_rate=1.0)
    assert all(bucket.allow() for _ in range(3))
    assert not bucket.allow()


def test_a_bucket_refuses_impossible_settings():
    with pytest.raises(ValueError, match="capacity"):
        TokenBucket(capacity=0, refill_rate=1.0)
    with pytest.raises(ValueError, match="refill rate"):
        TokenBucket(capacity=1, refill_rate=0)


def test_a_denied_caller_is_told_how_long_to_wait():
    bucket = TokenBucket(capacity=1, refill_rate=2.0)
    bucket.allow()
    wait = bucket.seconds_until()
    assert 0 < wait <= 0.5


def test_a_bucket_with_tokens_asks_for_no_wait():
    assert TokenBucket(capacity=2, refill_rate=1.0).seconds_until() == 0.0


def test_refill_restores_capacity_over_time(monkeypatch):
    clock = {"t": 1000.0}
    monkeypatch.setattr("p2pchase.infra.rate_limiter.time.monotonic", lambda: clock["t"])
    bucket = TokenBucket(capacity=2, refill_rate=1.0)
    assert bucket.allow() and bucket.allow()
    assert not bucket.allow()
    clock["t"] += 2.0
    assert bucket.allow()


def test_draining_forces_a_full_refill_wait():
    """After a 429 the server has spoken; spending a held token would defy it."""
    bucket = TokenBucket(capacity=5, refill_rate=1.0)
    bucket.drain()
    assert not bucket.allow()
    assert bucket.seconds_until() >= 0.9


def test_quota_counts_down_and_then_refuses():
    quota = QuotaManager(daily_limit=3)
    assert [quota.allow() for _ in range(4)] == [True, True, True, False]
    assert quota.used == 3
    assert quota.remaining == 0


def test_quota_resets_on_a_new_day(monkeypatch):
    clock = {"t": 86400.0 * 100}
    monkeypatch.setattr("p2pchase.infra.rate_limiter.time.time", lambda: clock["t"])
    quota = QuotaManager(daily_limit=1)
    assert quota.allow()
    assert not quota.allow()
    clock["t"] += 86400.0
    assert quota.allow()


def test_a_normal_send_rate_never_trips_the_detector():
    detector = DosDetector(window_sec=60.0, burst_threshold=12)
    assert all(detector.record() for _ in range(12))
    assert not detector.locked


def test_a_runaway_loop_locks_the_pipeline_permanently():
    """One report is sacrificed to save the account (rules 28, 29)."""
    detector = DosDetector(window_sec=60.0, burst_threshold=3)
    for _ in range(3):
        assert detector.record()
    assert detector.record() is False
    assert detector.locked
    assert "burst threshold" in detector.lock_reason
    assert detector.record() is False  # it never heals on its own


def test_old_events_fall_out_of_the_window(monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr("p2pchase.infra.rate_limiter.time.monotonic", lambda: clock["t"])
    detector = DosDetector(window_sec=10.0, burst_threshold=2)
    detector.record()
    detector.record()
    clock["t"] += 30.0
    assert detector.record()
    assert detector.recent == 1
    assert not detector.locked
