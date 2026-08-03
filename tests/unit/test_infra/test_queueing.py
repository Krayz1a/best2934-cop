"""The FIFO overflow queue and its backpressure signal (guidelines §5.3)."""

from __future__ import annotations

import threading

import pytest

from p2pchase.infra.queueing import OverflowQueue, QueueFullError


def test_a_ticket_is_issued_and_released():
    queue = OverflowQueue(max_depth=4)
    ticket = queue.take_ticket("gmail.send")
    assert queue.depth == 1
    assert queue.is_next(ticket)
    queue.release(ticket)
    assert queue.depth == 0
    assert queue.status().drained_total == 1


def test_service_is_strictly_first_in_first_out():
    """Letting a late caller through makes the wait unbounded for the unlucky."""
    queue = OverflowQueue(max_depth=4)
    first = queue.take_ticket("a")
    second = queue.take_ticket("b")
    assert queue.is_next(first)
    assert not queue.is_next(second)
    queue.release(first)
    assert queue.is_next(second)


def test_releasing_out_of_order_removes_only_that_ticket():
    """A caller that gave up must not make someone else's ticket vanish."""
    queue = OverflowQueue(max_depth=4)
    first = queue.take_ticket("a")
    second = queue.take_ticket("b")
    queue.release(second)
    assert queue.depth == 1
    assert queue.is_next(first)


def test_releasing_an_unknown_ticket_is_harmless():
    queue = OverflowQueue(max_depth=2)
    ticket = queue.take_ticket("a")
    queue.release(ticket)
    queue.release(ticket)
    assert queue.depth == 0


def test_a_full_queue_applies_backpressure_rather_than_buffering_forever():
    queue = OverflowQueue(max_depth=2)
    queue.take_ticket("a")
    queue.take_ticket("b")
    with pytest.raises(QueueFullError, match="backpressure"):
        queue.take_ticket("c")
    assert queue.status().rejected_total == 1


def test_backpressure_is_signalled_before_the_queue_is_actually_full():
    """A caller should be able to shed load while there is still room."""
    queue = OverflowQueue(max_depth=10, high_water_ratio=0.8)
    for _ in range(7):
        queue.take_ticket("x")
    assert not queue.backpressure
    queue.take_ticket("x")
    assert queue.backpressure


def test_status_reports_the_running_totals():
    queue = OverflowQueue(max_depth=3)
    ticket = queue.take_ticket("a")
    queue.release(ticket)
    status = queue.status().as_dict()
    assert status["enqueued_total"] == 1
    assert status["drained_total"] == 1
    assert status["max_depth"] == 3
    assert status["depth"] == 0


def test_concurrent_callers_do_not_corrupt_the_queue():
    """The runtime services the network on one thread while another reports."""
    queue = OverflowQueue(max_depth=200)
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(20):
                queue.release(queue.take_ticket("t"))
        except BaseException as error:  # noqa: BLE001 - recorded, asserted below
            errors.append(error)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert queue.depth == 0
    assert queue.status().enqueued_total == 160
    assert queue.status().drained_total == 160
