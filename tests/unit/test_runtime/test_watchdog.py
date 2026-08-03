"""Deadlines and the progress watchdog (book rules 6, 7)."""

from __future__ import annotations

import pytest

from p2pchase.runtime.watchdog import (
    DeadlineExceededError,
    TurnDeadline,
    Watchdog,
    WatchdogTrippedError,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_a_fresh_deadline_has_its_full_budget():
    clock = FakeClock()
    deadline = TurnDeadline(30.0, clock=clock)
    assert deadline.remaining() == pytest.approx(30.0)
    assert not deadline.expired
    deadline.check()


def test_time_consumes_the_budget():
    clock = FakeClock()
    deadline = TurnDeadline(30.0, clock=clock)
    clock.advance(10.0)
    assert deadline.remaining() == pytest.approx(20.0)
    assert deadline.elapsed == pytest.approx(10.0)


def test_remaining_never_goes_negative():
    clock = FakeClock()
    deadline = TurnDeadline(5.0, clock=clock)
    clock.advance(50.0)
    assert deadline.remaining() == 0.0


def test_an_expired_deadline_names_what_ran_out_of_time():
    clock = FakeClock()
    deadline = TurnDeadline(5.0, clock=clock)
    clock.advance(6.0)
    with pytest.raises(DeadlineExceededError, match="waiting for their reveal"):
        deadline.check("waiting for their reveal")


def test_a_deadline_can_be_restarted():
    clock = FakeClock()
    deadline = TurnDeadline(5.0, clock=clock)
    clock.advance(4.0)
    deadline.reset()
    assert deadline.remaining() == pytest.approx(5.0)


def test_a_quiet_match_is_not_yet_a_dead_one():
    clock = FakeClock()
    dog = Watchdog(timeout_sec=60.0, clock=clock)
    clock.advance(59.0)
    assert not dog.tripped
    dog.check()


def test_progress_resets_the_watchdog():
    clock = FakeClock()
    dog = Watchdog(timeout_sec=60.0, clock=clock)
    clock.advance(50.0)
    dog.beat()
    clock.advance(50.0)
    assert not dog.tripped
    assert dog.beats == 1


def test_a_stalled_match_trips_and_explains_itself():
    """Waiting politely loses the game just as thoroughly as playing badly."""
    clock = FakeClock()
    dog = Watchdog(timeout_sec=60.0, clock=clock)
    clock.advance(61.0)
    with pytest.raises(WatchdogTrippedError, match="rule 6"):
        dog.check("sub-game 3")
    assert "sub-game 3" in dog.tripped_reason
    assert "technical loss for both teams" in dog.tripped_reason


def test_traffic_alone_does_not_count_as_progress():
    """An opponent answering instantly with refusals must still trip it."""
    clock = FakeClock()
    dog = Watchdog(timeout_sec=10.0, clock=clock)
    for _ in range(100):
        clock.advance(0.2)  # busy, but no beat() -- nothing actually completed
    assert dog.idle_for == pytest.approx(20.0)
    assert dog.tripped
