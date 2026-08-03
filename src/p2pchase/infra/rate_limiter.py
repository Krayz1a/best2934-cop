"""The three rate-control primitives behind the Gatekeeper (book ch9.3.1).

Each guards against a different failure, and they are separate classes because
they fail at different time scales:

``TokenBucket``   -- smooths bursts over seconds.
``QuotaManager``  -- caps total volume over a day.
``DosDetector``   -- spots a runaway loop and opens the circuit permanently.

A note the book insists on: the "tokens" here are RATE tokens for load shaping.
They have nothing to do with language-model tokens, which are metered
separately, nor with OAuth tokens.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    """Classic token bucket: continuous refill, one token per call.

    Input:  ``capacity`` (burst tolerated after a quiet spell),
            ``refill_rate`` (sustainable long-run average, in tokens/second).
    Output: :meth:`allow` grants or denies; :meth:`seconds_until` says how long
            a denied caller must wait.
    Setup:  starts full, so the first burst after startup is not penalised.

        tokens <- min(C, tokens + r * dt),    allow <=> tokens >= 1
    """

    capacity: float
    refill_rate: float
    tokens: float = field(init=False)
    last: float = field(init=False)

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("token bucket capacity must be positive")
        if self.refill_rate <= 0:
            raise ValueError("token bucket refill rate must be positive")
        self.tokens = float(self.capacity)
        self.last = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        self.tokens = min(self.capacity, self.tokens + (now - self.last) * self.refill_rate)
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
        return (cost - self.tokens) / self.refill_rate

    def drain(self) -> None:
        """Empty the bucket, forcing a full refill wait.

        Used after a 429: the server has told us we are over its limit, so the
        next attempt must wait for genuine refill rather than spend a token we
        happen to be holding.
        """
        self._refill()
        self.tokens = 0.0


@dataclass
class QuotaManager:
    """Daily counter -- the last line of defence before account suspension."""

    daily_limit: int = 200
    _count: int = 0
    _day: int = field(default_factory=lambda: int(time.time() // 86400))

    def _roll_over(self) -> None:
        today = int(time.time() // 86400)
        if today != self._day:
            self._day, self._count = today, 0

    def allow(self) -> bool:
        """Consume one unit of today's quota, or refuse when it is spent."""
        self._roll_over()
        if self._count >= self.daily_limit:
            return False
        self._count += 1
        return True

    @property
    def used(self) -> int:
        self._roll_over()
        return self._count

    @property
    def remaining(self) -> int:
        return max(0, self.daily_limit - self.used)


@dataclass
class DosDetector:
    """Detects send patterns that indicate a bug rather than a real match.

    A legitimate agent sends a handful of reports per match. A runaway loop
    sends dozens per minute. Crossing ``burst_threshold`` inside ``window_sec``
    is treated as a defect in our own code, so the circuit opens permanently
    for this process -- sacrificing one report to save the account (rules 28,
    29). It never closes again on its own, because a self-healing breaker in
    front of a buggy loop just fires the loop again more slowly.
    """

    window_sec: float = 60.0
    burst_threshold: int = 12
    locked: bool = False
    lock_reason: str = ""
    _events: deque[float] = field(default_factory=deque)

    def record(self) -> bool:
        """Register a send attempt. Returns ``False`` once locked."""
        if self.locked:
            return False
        now = time.monotonic()
        self._events.append(now)
        while self._events and now - self._events[0] > self.window_sec:
            self._events.popleft()
        if len(self._events) > self.burst_threshold:
            self.locked = True
            self.lock_reason = (
                f"{len(self._events)} calls in {self.window_sec:.0f}s exceeds the burst "
                f"threshold of {self.burst_threshold}; locking the pipeline to protect "
                f"the account"
            )
            return False
        return True

    @property
    def recent(self) -> int:
        return len(self._events)
