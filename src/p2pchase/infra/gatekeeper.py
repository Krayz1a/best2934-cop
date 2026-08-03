"""The Gatekeeper: three cumulative guards in front of the Gmail API (book ch9.3.1).

Autonomous reporting is a blessing and a trap. It guarantees uniform, immediate
delivery -- and it hands a live mail account to code that might contain a bug.
What happens when a loop starts firing thousands of messages a minute? Google
answers with HTTP 429, and blind retrying past a 429 gets the account suspended.

So an outgoing report crosses three gates in series, failing as early as
possible:

    report -> QuotaManager -> TokenBucket -> DosDetector -> Gmail API
                 |               |               |
             Rejected         Blocked         LOCKED
            (quota full)     (no token)      (anomaly)

The DOS detector is the one that matters most: on detecting a runaway pattern it
locks the whole pipe, sacrificing one report to save the account (rules 28, 29).

Terminology, because the book warns about it explicitly: the "tokens" here are
RATE tokens for load shaping. They have nothing to do with language-model
tokens, which are metered separately, nor with OAuth tokens.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from .. import constants as K


class GateDecision(str, Enum):
    ALLOW = "allow"
    QUOTA_EXCEEDED = "quota_exceeded"
    RATE_LIMITED = "rate_limited"
    LOCKED = "locked"


class GatekeeperLocked(RuntimeError):
    """Raised when the DOS detector has sealed the pipeline."""


@dataclass
class TokenBucket:
    """Classic token bucket: continuous refill, one token per report.

        tokens <- min(C, tokens + r * dt),    allow <=> tokens >= 1

    ``capacity`` sets the burst we tolerate after a quiet spell; ``refill_rate``
    sets the sustainable long-run average, which must stay under Google's quota.
    """

    capacity: float
    refill_rate: float
    tokens: float = field(init=False)
    last: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = float(self.capacity)
        self.last = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last = now

    def allow(self, cost: float = 1.0) -> bool:
        self._refill()
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def seconds_until(self, cost: float = 1.0) -> float:
        """How long the caller should back off before retrying."""
        self._refill()
        if self.tokens >= cost:
            return 0.0
        return (cost - self.tokens) / self.refill_rate if self.refill_rate > 0 else float("inf")


@dataclass
class QuotaManager:
    """Daily counter -- the last line of defence before account suspension."""

    daily_limit: int = 200
    _count: int = 0
    _day: int = field(default_factory=lambda: int(time.time() // 86400))

    def allow(self) -> bool:
        today = int(time.time() // 86400)
        if today != self._day:
            self._day, self._count = today, 0
        if self._count >= self.daily_limit:
            return False
        self._count += 1
        return True

    @property
    def used(self) -> int:
        return self._count


@dataclass
class DosDetector:
    """Detects send patterns that indicate a bug rather than a real match.

    A legitimate agent sends a handful of reports per match. A runaway loop
    sends dozens per minute. Crossing ``burst_threshold`` inside ``window_sec``
    is treated as a defect in our own code, and the circuit is opened
    permanently for this process -- backpressure plus circuit-breaker.
    """

    window_sec: float = 60.0
    burst_threshold: int = 12
    locked: bool = False
    lock_reason: str = ""
    _events: deque[float] = field(default_factory=deque)

    def record(self) -> bool:
        """Register a send attempt. Returns False once locked."""
        if self.locked:
            return False
        now = time.monotonic()
        self._events.append(now)
        while self._events and now - self._events[0] > self.window_sec:
            self._events.popleft()
        if len(self._events) > self.burst_threshold:
            self.locked = True
            self.lock_reason = (
                f"{len(self._events)} sends in {self.window_sec:.0f}s exceeds "
                f"the burst threshold of {self.burst_threshold}; locking the "
                f"pipeline to protect the account"
            )
            return False
        return True


@dataclass
class Gatekeeper:
    """The three gates, in series."""

    quota: QuotaManager = field(default_factory=QuotaManager)
    bucket: TokenBucket = field(default_factory=lambda: TokenBucket(capacity=5, refill_rate=0.5))
    dos: DosDetector = field(default_factory=DosDetector)
    retry_backoff_sec: int = K.RETRY_BACKOFF_SEC
    max_retries: int = K.MAX_RETRIES

    def check(self) -> tuple[GateDecision, str]:
        """Evaluate all three gates without consuming budget on a later failure.

        Order matters: the cheapest, most permanent guard runs first so a
        locked pipeline never burns quota or tokens.
        """
        if self.dos.locked:
            return GateDecision.LOCKED, self.dos.lock_reason
        if not self.quota.allow():
            return GateDecision.QUOTA_EXCEEDED, (
                f"daily quota of {self.quota.daily_limit} reports exhausted"
            )
        if not self.bucket.allow():
            wait = self.bucket.seconds_until()
            return GateDecision.RATE_LIMITED, f"rate limited; retry in {wait:.1f}s"
        if not self.dos.record():
            return GateDecision.LOCKED, self.dos.lock_reason
        return GateDecision.ALLOW, "ok"

    def honour_429(self) -> float:
        """Back off after a 429 instead of hammering (book ch9.3.3, iron rule).

        Draining the bucket means the next attempt has to wait for genuine
        refill, which is exactly the behaviour Google's quota expects.
        """
        self.bucket.tokens = 0.0
        return float(self.retry_backoff_sec)


def build_gatekeeper(config: dict) -> Gatekeeper:
    """Construct from the agreed rate-limiter section of ``game.json``."""
    rl = config.get("rate_limiter_gatekeeper", {})
    rpm = int(rl.get("requests_per_minute", K.REQUESTS_PER_MINUTE))
    return Gatekeeper(
        # The agreed value is a per-minute API ceiling; the bucket is sized well
        # below it because reports are rare and bursts are the real hazard.
        bucket=TokenBucket(capacity=float(min(5, rpm)), refill_rate=rpm / 60.0),
        retry_backoff_sec=int(rl.get("retry_backoff_sec", K.RETRY_BACKOFF_SEC)),
        max_retries=int(rl.get("max_retries", K.MAX_RETRIES)),
    )
