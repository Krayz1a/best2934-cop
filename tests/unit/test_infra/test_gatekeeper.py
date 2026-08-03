"""The Gatekeeper: the single door in front of every external API call."""

from __future__ import annotations

import pytest

from p2pchase.infra.gatekeeper import (
    ApiGatekeeper,
    GateDecision,
    GatekeeperLockedError,
    QuotaExceededError,
    build_gatekeeper,
)
from p2pchase.infra.queueing import OverflowQueue
from p2pchase.infra.rate_limiter import DosDetector, QuotaManager, TokenBucket
from p2pchase.infra.retrying import RetryPolicy


class FakeHttpError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status_code = status


def make_gate(**overrides) -> ApiGatekeeper:
    """A gatekeeper whose clocks never really sleep."""
    defaults = {
        "bucket": TokenBucket(capacity=5, refill_rate=100.0),
        "quota": QuotaManager(daily_limit=10),
        "dos": DosDetector(window_sec=60.0, burst_threshold=50),
        "queue": OverflowQueue(max_depth=10),
        "retry": RetryPolicy(max_retries=2, backoff_sec=0.0, sleep=lambda _s: None),
        "sleep": lambda _s: None,
    }
    defaults.update(overrides)
    return ApiGatekeeper(**defaults)


def test_a_healthy_call_passes_straight_through():
    gate = make_gate()
    assert gate.execute(lambda: "sent", gate_label="gmail.send") == "sent"
    assert gate.calls[-1].ok
    assert gate.calls[-1].decision is GateDecision.ALLOW


def test_arguments_reach_the_wrapped_call():
    gate = make_gate()
    assert gate.execute(lambda a, b=0: a + b, 2, b=3) == 5


def test_every_call_is_recorded_for_monitoring():
    gate = make_gate()
    gate.execute(lambda: None, gate_label="first")
    gate.execute(lambda: None, gate_label="second")
    assert [c.label for c in gate.calls] == ["first", "second"]


def test_an_exhausted_daily_quota_refuses_rather_than_waits():
    gate = make_gate(quota=QuotaManager(daily_limit=1))
    gate.execute(lambda: None)
    with pytest.raises(QuotaExceededError, match="daily quota"):
        gate.execute(lambda: None)
    assert gate.calls[-1].decision is GateDecision.QUOTA_EXCEEDED


def test_a_locked_pipeline_never_burns_quota():
    """The DOS gate runs first precisely so a locked pipe costs nothing."""
    quota = QuotaManager(daily_limit=10)
    dos = DosDetector(window_sec=60.0, burst_threshold=1)
    gate = make_gate(quota=quota, dos=dos)
    gate.execute(lambda: None)
    with pytest.raises(GatekeeperLockedError):
        gate.execute(lambda: None)
    used_after_lock = quota.used
    with pytest.raises(GatekeeperLockedError):
        gate.execute(lambda: None)
    assert quota.used == used_after_lock


def test_overflow_is_queued_not_rejected():
    """Guidelines §5.3: a rate limit delays a call, it does not cancel it."""
    gate = make_gate(bucket=TokenBucket(capacity=1, refill_rate=1000.0))
    gate.execute(lambda: None)
    assert gate.execute(lambda: "second") == "second"
    assert gate.calls[-1].decision is GateDecision.QUEUED
    assert gate.get_queue_status().depth == 0  # the ticket was released


def test_waiting_forever_is_not_an_option():
    gate = make_gate(bucket=TokenBucket(capacity=1, refill_rate=1e-9), max_wait_sec=0.0)
    gate.execute(lambda: None)
    with pytest.raises(TimeoutError, match="rate token"):
        gate.execute(lambda: None)


def test_a_transient_failure_is_retried():
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise FakeHttpError(503)
        return "ok"

    assert make_gate().execute(flaky) == "ok"
    assert attempts["n"] == 3


def test_a_permanent_failure_is_not_retried():
    attempts = {"n": 0}

    def forbidden():
        attempts["n"] += 1
        raise FakeHttpError(401)

    with pytest.raises(FakeHttpError):
        make_gate().execute(forbidden)
    assert attempts["n"] == 1


def test_a_failed_call_is_still_recorded():
    gate = make_gate()
    with pytest.raises(FakeHttpError):
        gate.execute(lambda: (_ for _ in ()).throw(FakeHttpError(401)))
    assert gate.calls[-1].ok is False
    assert "FakeHttpError" in gate.calls[-1].error


def test_a_429_drains_the_bucket_instead_of_merely_waiting():
    """Blind retrying past a 429 is what gets an account suspended."""
    gate = make_gate()
    assert gate.bucket.tokens > 0
    backoff = gate.honour_429()
    assert gate.bucket.tokens == 0.0
    assert backoff == pytest.approx(gate.retry.backoff_sec)


def test_check_reports_health_without_consuming_anything():
    gate = make_gate(quota=QuotaManager(daily_limit=1))
    assert gate.check() == (GateDecision.ALLOW, "ok")
    assert gate.quota.used == 0


def test_it_is_built_from_configuration_never_from_literals(loaded_config):
    gate = build_gatekeeper(loaded_config.rate_limits, "gmail")
    assert gate.queue.max_depth == 100
    assert gate.quota.daily_limit == 200
    assert gate.retry.max_retries == 3
