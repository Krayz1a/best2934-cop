"""The Gatekeeper: the single door every external API call goes through.

Autonomous reporting is a blessing and a trap. It guarantees uniform, immediate
delivery -- and it hands a live mail account to code that might contain a bug.
What happens when a loop starts firing thousands of messages a minute? Google
answers with HTTP 429, and blind retrying past a 429 gets the account suspended.

So every outgoing call crosses four gates, failing as early as possible:

    call -> DosDetector -> QuotaManager -> TokenBucket -> OverflowQueue -> API
               |               |               |              |
             LOCKED         Rejected      wait for a       fair FIFO
            (anomaly)      (quota full)      token       (never dropped)

Order matters. The DOS detector runs first because it is the cheapest and most
permanent guard -- a locked pipeline must never burn quota. The overflow queue
runs last because it is the only gate that *waits* rather than refuses: rate
limits delay a call, they do not cancel it (guidelines §5.3).

Guidelines §5.1 requires that no call bypass this class, that limits be checked
before every call, that overflow be queued rather than rejected, and that every
call be recorded for monitoring. :meth:`ApiGatekeeper.execute` is the only
public path, and it does all four.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..shared.rate_limits import DEFAULT_RATE_LIMITS, service_limits
from .queueing import OverflowQueue, QueueStatus
from .rate_limiter import DosDetector, QuotaManager, TokenBucket
from .retrying import RetryPolicy

LOGGER = logging.getLogger(__name__)


class GateDecision(str, Enum):
    ALLOW = "allow"
    QUEUED = "queued"
    QUOTA_EXCEEDED = "quota_exceeded"
    LOCKED = "locked"


class GatekeeperLocked(RuntimeError):
    """The DOS detector has sealed the pipeline for this process."""


class QuotaExceeded(RuntimeError):
    """Today's allowance is spent; waiting will not help before midnight."""


@dataclass(frozen=True)
class CallRecord:
    """One monitored call, kept so a post-match audit can reconstruct load."""

    label: str
    decision: GateDecision
    waited_sec: float
    duration_sec: float
    attempts: int
    ok: bool
    error: str = ""


@dataclass
class ApiGatekeeper:
    """Centralized API call manager.

    Input:  a callable plus its arguments, via :meth:`execute`.
    Output: the callable's return value, or an exception that names which gate
            refused and why.
    Setup:  the four guards, a retry policy, and ``max_wait_sec`` -- the point
            at which waiting for a token is worse than failing loudly.
    """

    bucket: TokenBucket
    quota: QuotaManager = field(default_factory=QuotaManager)
    dos: DosDetector = field(default_factory=DosDetector)
    queue: OverflowQueue = field(default_factory=OverflowQueue)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    max_wait_sec: float = 120.0
    sleep: Callable[[float], None] = time.sleep
    calls: list[CallRecord] = field(default_factory=list)

    # ------------------------------------------------------------------ gates
    def check(self) -> tuple[GateDecision, str]:
        """Evaluate the non-waiting gates without consuming anything."""
        if self.dos.locked:
            return GateDecision.LOCKED, self.dos.lock_reason
        if self.quota.remaining <= 0:
            return GateDecision.QUOTA_EXCEEDED, (
                f"daily quota of {self.quota.daily_limit} calls exhausted"
            )
        return GateDecision.ALLOW, "ok"

    def honour_429(self) -> float:
        """Back off after a 429 instead of hammering (book ch9.3.3, iron rule)."""
        self.bucket.drain()
        LOGGER.warning("429 received; bucket drained, backing off %.1fs", self.retry.backoff_sec)
        return float(self.retry.backoff_sec)

    def get_queue_status(self) -> QueueStatus:
        """Queue depth and statistics (guidelines §5.1 interface)."""
        return self.queue.status()

    # ---------------------------------------------------------------- execute
    def execute(self, api_call: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute an external API call through all four gates."""
        label = str(kwargs.pop("gate_label", getattr(api_call, "__name__", "api_call")))

        decision, reason = self.check()
        if decision is GateDecision.LOCKED:
            self._record(label, decision, 0.0, 0.0, 0, False, reason)
            raise GatekeeperLocked(reason)
        if decision is GateDecision.QUOTA_EXCEEDED:
            self._record(label, decision, 0.0, 0.0, 0, False, reason)
            raise QuotaExceeded(reason)

        waited = self._await_turn(label)
        if not self.dos.record():
            self._record(label, GateDecision.LOCKED, waited, 0.0, 0, False, self.dos.lock_reason)
            raise GatekeeperLocked(self.dos.lock_reason)
        self.quota.allow()

        started = time.monotonic()
        try:
            result, attempts = self.retry.run(api_call, args, kwargs, self.honour_429)
        except Exception as error:
            self._record(label, GateDecision.ALLOW, waited, time.monotonic() - started,
                         self.retry.max_retries + 1, False, f"{type(error).__name__}: {error}")
            raise
        self._record(label, GateDecision.ALLOW if waited == 0 else GateDecision.QUEUED,
                     waited, time.monotonic() - started, attempts, True)
        return result

    # ----------------------------------------------------------------- internals
    def _await_turn(self, label: str) -> float:
        """Queue for a rate token and wait our turn. Returns seconds waited."""
        if self.bucket.allow():
            return 0.0

        ticket = self.queue.take_ticket(label)
        if self.queue.backpressure:
            LOGGER.warning("gatekeeper queue at %d/%d — applying backpressure",
                           self.queue.depth, self.queue.max_depth)
        started = time.monotonic()
        try:
            while True:
                waited = time.monotonic() - started
                if waited >= self.max_wait_sec:
                    raise TimeoutError(
                        f"waited {waited:.0f}s for a rate token (limit {self.max_wait_sec:.0f}s); "
                        f"queue depth {self.queue.depth}"
                    )
                if self.queue.is_next(ticket) and self.bucket.allow():
                    return waited
                self.sleep(min(0.25, self.bucket.seconds_until()) or 0.05)
        finally:
            self.queue.release(ticket)

    def _record(self, label: str, decision: GateDecision, waited: float, duration: float,
                attempts: int, ok: bool, error: str = "") -> None:
        """Every call is logged for monitoring (guidelines §5.1)."""
        self.calls.append(CallRecord(label, decision, round(waited, 3), round(duration, 3),
                                     attempts, ok, error))
        LOGGER.info("gate=%s label=%s waited=%.2fs took=%.2fs attempts=%d ok=%s %s",
                    decision.value, label, waited, duration, attempts, ok, error)


def build_gatekeeper(rate_limits: dict[str, Any] | None = None,
                     service: str = "default") -> ApiGatekeeper:
    """Construct a Gatekeeper from ``config/rate_limits.json`` -- never from literals."""
    limits = service_limits(rate_limits or DEFAULT_RATE_LIMITS, service)
    rpm = float(limits["requests_per_minute"])
    return ApiGatekeeper(
        bucket=TokenBucket(capacity=float(limits.get("bucket_capacity", 5)),
                           refill_rate=rpm / 60.0),
        quota=QuotaManager(daily_limit=int(limits["daily_limit"])),
        dos=DosDetector(window_sec=float(limits["burst_window_seconds"]),
                        burst_threshold=int(limits["burst_threshold"])),
        queue=OverflowQueue(max_depth=int(limits["queue_depth"])),
        retry=RetryPolicy(max_retries=int(limits["max_retries"]),
                          backoff_sec=float(limits["retry_after_seconds"])),
    )
