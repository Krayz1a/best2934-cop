"""Retry policy for external calls (guidelines §5.1 -- "retry on transient failures").

The distinction that matters is transient versus permanent. Retrying a 429 or a
503 is correct: the service is telling us to come back later. Retrying a 401 or
a malformed request is not -- it will fail identically every time while burning
quota and pushing us toward the DOS threshold.

The book states the iron rule plainly: blind retrying past a 429 gets the
account suspended. So a 429 does not merely delay the next attempt, it drains
the token bucket, forcing a wait for genuine refill.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

#: HTTP statuses worth retrying: rate limiting and server-side faults.
TRANSIENT_STATUSES: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})


def status_of(error: BaseException) -> int | None:
    """Best-effort HTTP status extraction across client libraries.

    Google's client, httpx and requests all report status differently, and none
    of them is a dependency of this module -- so we duck-type rather than
    import, and fall back to scanning the message only for the codes we act on.
    """
    for attribute in ("status_code", "status", "code", "resp_status"):
        value = getattr(error, attribute, None)
        if isinstance(value, int):
            return value
    response = getattr(error, "response", None)
    if response is not None:
        value = getattr(response, "status_code", None)
        if isinstance(value, int):
            return value
    text = str(error)
    for status in TRANSIENT_STATUSES:
        if str(status) in text:
            return status
    return None


def is_transient(error: BaseException) -> bool:
    """True when retrying could plausibly succeed."""
    status = status_of(error)
    if status is not None:
        return status in TRANSIENT_STATUSES
    return isinstance(error, TimeoutError | ConnectionError)


def is_rate_limited(error: BaseException) -> bool:
    """True specifically for HTTP 429, which demands a bucket drain."""
    return status_of(error) == 429


@dataclass
class RetryPolicy:
    """Exponential backoff with a hard attempt ceiling.

    Input:  ``max_retries`` (attempts *after* the first), ``backoff_sec`` (the
            base delay), ``multiplier`` (growth per attempt).
    Output: :meth:`delay_for` -- how long to wait before attempt ``n``.
    Setup:  ``sleep`` is injectable so tests never actually wait.
    """

    max_retries: int = 3
    backoff_sec: float = 5.0
    multiplier: float = 2.0
    sleep: Callable[[float], None] = time.sleep

    def delay_for(self, attempt: int) -> float:
        """Delay before retry number ``attempt`` (1-based)."""
        return self.backoff_sec * (self.multiplier ** max(0, attempt - 1))

    def run(
        self,
        call: Callable[..., Any],
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        on_rate_limit: Callable[[], float] | None = None,
    ) -> tuple[Any, int]:
        """Invoke ``call``, retrying transient failures. Returns (result, attempts).

        ``on_rate_limit`` is the hook the Gatekeeper uses to drain its bucket on
        a 429; it returns the number of seconds to wait, overriding the normal
        backoff because the server's own signal outranks our schedule.
        """
        kwargs = dict(kwargs or {})
        last_error: BaseException | None = None

        for attempt in range(1, self.max_retries + 2):
            try:
                return call(*args, **kwargs), attempt
            except Exception as error:  # noqa: BLE001 -- classified below, then re-raised
                last_error = error
                if not is_transient(error) or attempt > self.max_retries:
                    raise
                delay = self.delay_for(attempt)
                if is_rate_limited(error) and on_rate_limit is not None:
                    delay = max(delay, on_rate_limit())
                self.sleep(delay)

        raise RuntimeError("retry loop exhausted without a verdict") from last_error
