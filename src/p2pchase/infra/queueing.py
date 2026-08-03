"""FIFO overflow queue with backpressure (guidelines §5.3).

The rule this module exists to satisfy is specific: when a rate limit is
reached the Gatekeeper must *queue* the request, not reject it and not crash.
Rejecting looks safer and is worse -- the caller either loses the report or
retries immediately, which is precisely the runaway pattern the DOS detector
is there to catch.

So overflow waits its turn. Fairness is strict FIFO, because the alternative
(letting a late caller through while an earlier one waits) makes the delay
unbounded for whoever is unlucky. The queue is bounded: past ``max_depth`` the
system is genuinely overloaded and the honest answer is backpressure, signalled
to the caller rather than hidden behind an ever-growing buffer.

Thread safety matters here (guidelines §15.2): the peer runtime services the
network on one thread while the reporter may enqueue from another, so every
mutation is taken under a single re-entrant lock.
"""

from __future__ import annotations

import itertools
import threading
from collections import deque
from dataclasses import dataclass, field


class QueueFull(RuntimeError):
    """Raised when the overflow queue is at capacity -- genuine backpressure."""


@dataclass(frozen=True)
class QueueStatus:
    """Snapshot of queue health, returned by ``ApiGatekeeper.get_queue_status``."""

    depth: int
    max_depth: int
    enqueued_total: int
    drained_total: int
    rejected_total: int
    backpressure: bool

    def as_dict(self) -> dict[str, int | bool]:
        return {
            "depth": self.depth,
            "max_depth": self.max_depth,
            "enqueued_total": self.enqueued_total,
            "drained_total": self.drained_total,
            "rejected_total": self.rejected_total,
            "backpressure": self.backpressure,
        }


@dataclass
class Ticket:
    """A caller's place in line."""

    number: int
    label: str


@dataclass
class OverflowQueue:
    """Bounded FIFO admission queue.

    Input:  ``max_depth`` -- the point past which backpressure is honest.
    Output: :meth:`take_ticket` / :meth:`is_next` / :meth:`release` implement a
            fair turnstile; :meth:`status` reports health.
    Setup:  ``high_water_ratio`` -- the fill level at which the queue starts
            reporting backpressure, before it is actually full, so a caller can
            shed load while there is still room to.
    """

    max_depth: int = 100
    high_water_ratio: float = 0.8
    _waiting: deque[Ticket] = field(default_factory=deque)
    _counter: itertools.count = field(default_factory=lambda: itertools.count(1))
    _lock: threading.RLock = field(default_factory=threading.RLock)
    enqueued_total: int = 0
    drained_total: int = 0
    rejected_total: int = 0

    def take_ticket(self, label: str = "") -> Ticket:
        """Join the line, or raise :class:`QueueFull` when genuinely overloaded."""
        with self._lock:
            if len(self._waiting) >= self.max_depth:
                self.rejected_total += 1
                raise QueueFull(
                    f"overflow queue is full ({self.max_depth} waiting); "
                    f"applying backpressure instead of buffering without bound"
                )
            ticket = Ticket(number=next(self._counter), label=label)
            self._waiting.append(ticket)
            self.enqueued_total += 1
            return ticket

    def is_next(self, ticket: Ticket) -> bool:
        """True when this ticket is at the head of the line."""
        with self._lock:
            return bool(self._waiting) and self._waiting[0].number == ticket.number

    def release(self, ticket: Ticket) -> None:
        """Leave the line, whether the call succeeded or failed.

        Removal is by ticket number rather than ``popleft`` so that a caller
        that gave up mid-wait cannot make another caller's ticket vanish.
        """
        with self._lock:
            for index, waiting in enumerate(self._waiting):
                if waiting.number == ticket.number:
                    del self._waiting[index]
                    self.drained_total += 1
                    return

    @property
    def depth(self) -> int:
        with self._lock:
            return len(self._waiting)

    @property
    def backpressure(self) -> bool:
        """True once the queue is deep enough that callers should back off."""
        return self.depth >= max(1, int(self.max_depth * self.high_water_ratio))

    def status(self) -> QueueStatus:
        with self._lock:
            return QueueStatus(
                depth=len(self._waiting),
                max_depth=self.max_depth,
                enqueued_total=self.enqueued_total,
                drained_total=self.drained_total,
                rejected_total=self.rejected_total,
                backpressure=self.backpressure,
            )
