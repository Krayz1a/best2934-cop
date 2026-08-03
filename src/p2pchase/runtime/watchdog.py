"""Deadlines and the watchdog (book rules 6, 7; Appendix F Table 18).

A two-party protocol with no referee has one catastrophic failure mode: waiting
forever. If the opponent's process dies mid-turn, a naive peer blocks until
somebody notices, and rule 6 makes an unfinished sub-game a technical loss for
*both* sides. Neither team can afford to be the one still politely waiting.

Two independent clocks therefore run, and they answer different questions:

``TurnDeadline``  -- "has this single message taken too long?" (default 30s)
``Watchdog``      -- "has the match as a whole stopped making progress?" (60s)

The second exists because the first is not enough. An opponent that answers
every message instantly with a refusal, or loops resending the same phase, never
trips a per-message timeout while the match goes nowhere. The watchdog measures
*progress*, not traffic: it is fed only when a step actually completes.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


class DeadlineExceededError(TimeoutError):
    """A single operation ran past its allotted time."""


class WatchdogTrippedError(TimeoutError):
    """The match stopped making progress; abort rather than hang (rule 6)."""


@dataclass
class TurnDeadline:
    """A per-operation stopwatch.

    Input:  ``seconds`` -- the agreed response timeout.
    Output: :meth:`remaining` / :meth:`expired` / :meth:`check`.
    Setup:  ``clock`` is injectable so tests are instant and deterministic.
    """

    seconds: float
    clock: object = field(default=None, repr=False)
    started: float = field(init=False)

    def __post_init__(self) -> None:
        self._now = self.clock or time.monotonic  # type: ignore[assignment]
        self.started = self._now()

    def reset(self) -> None:
        self.started = self._now()

    @property
    def elapsed(self) -> float:
        return self._now() - self.started

    def remaining(self) -> float:
        """Seconds left, floored at zero."""
        return max(0.0, self.seconds - self.elapsed)

    @property
    def expired(self) -> bool:
        return self.elapsed >= self.seconds

    def check(self, what: str = "operation") -> None:
        """Raise if the deadline has passed, naming what ran out of time."""
        if self.expired:
            raise DeadlineExceededError(
                f"{what} exceeded its {self.seconds:.0f}s deadline "
                f"(elapsed {self.elapsed:.1f}s)"
            )


@dataclass
class Watchdog:
    """Progress monitor for a whole sub-game.

    Input:  :meth:`beat` -- called only when a step genuinely completes.
    Output: :meth:`check` raises once no progress has been made for
            ``timeout_sec``.
    Setup:  ``timeout_sec`` (default 60s, Appendix F) and an injectable clock.
    """

    timeout_sec: float = 60.0
    clock: object = field(default=None, repr=False)
    last_progress: float = field(init=False)
    beats: int = 0
    tripped_reason: str = ""

    def __post_init__(self) -> None:
        self._now = self.clock or time.monotonic  # type: ignore[assignment]
        self.last_progress = self._now()

    def beat(self) -> None:
        """Record real progress. Traffic alone must never call this."""
        self.last_progress = self._now()
        self.beats += 1

    @property
    def idle_for(self) -> float:
        return self._now() - self.last_progress

    @property
    def tripped(self) -> bool:
        return self.idle_for >= self.timeout_sec

    def check(self, context: str = "match") -> None:
        """Raise once the match has stalled, so the peer can abort cleanly."""
        if self.tripped:
            self.tripped_reason = (
                f"{context} made no progress for {self.idle_for:.0f}s "
                f"(watchdog limit {self.timeout_sec:.0f}s); aborting rather than "
                f"hanging, since an unfinished sub-game is a technical loss for "
                f"both teams (rule 6)"
            )
            raise WatchdogTrippedError(self.tripped_reason)
