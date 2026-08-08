"""Waiting on a reference-v3 inbox: what discharges a deadline and what does not.

One deadline per EXPECTED message. This module exists because the two tempting
shortcuts are both wrong in the same direction -- they let a driver believe the
game is progressing while it is not:

* popping the head of the queue treats *any* arrival as the one awaited, so a
  peer resending step 3 forever keeps a driver waiting on step 4 alive and
  makes no progress;
* accepting a step we have already applied advances our board on one of their
  moves counted twice, which desynchronises the two chains at the audit.

The third case is the one it would be easy to get backwards: a turn for a
*later* step is early, not wrong, and must survive in the queue. Dropping it
loses a move we still owe an answer to.
"""

from __future__ import annotations

import asyncio

import pytest

from p2pchase.mcp.reference_v3_server import Inboxes
from p2pchase.runtime import reference_inbox
from p2pchase.runtime.peer import OpponentFinishedError
from p2pchase.runtime.watchdog import DeadlineExceededError, Watchdog


def _turn(step: int) -> dict:
    return {"step": step, "sender": "thief", "commit": "a" * 64, "hint": "",
            "smell_grid": {}, "timestamp": "2026-08-08T19:00:00Z"}


def _run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------ take_turn
def test_the_expected_step_is_taken_out_of_the_queue():
    inboxes = Inboxes()
    inboxes.turns.append(_turn(3))
    assert reference_inbox.take_turn_at(inboxes, 3)["step"] == 3
    assert not inboxes.turns, "a message answered twice is a move played twice"


def test_a_step_we_have_already_passed_is_dropped():
    inboxes = Inboxes()
    inboxes.turns.append(_turn(1))
    assert reference_inbox.take_turn_at(inboxes, 4) is None
    assert not inboxes.turns


def test_a_step_we_have_not_reached_yet_is_kept_for_later():
    """Early is not wrong. We still owe that turn an answer when we get there."""
    inboxes = Inboxes()
    inboxes.turns.append(_turn(9))
    assert reference_inbox.take_turn_at(inboxes, 4) is None
    assert [t["step"] for t in inboxes.turns] == [9]


def test_the_expected_step_is_found_behind_a_stale_one():
    """Popping the head blind would have thrown the awaited message away."""
    inboxes = Inboxes()
    inboxes.turns.extend([_turn(1), _turn(5), _turn(7)])
    assert reference_inbox.take_turn_at(inboxes, 5)["step"] == 5
    assert [t["step"] for t in inboxes.turns] == [7]


def test_only_the_first_copy_of_a_duplicate_is_taken():
    """A retrying peer sends the same step twice; it is still one move."""
    inboxes = Inboxes()
    inboxes.turns.extend([_turn(2), _turn(2)])
    assert reference_inbox.take_turn_at(inboxes, 2)["step"] == 2
    assert [t["step"] for t in inboxes.turns] == [2]


def test_a_turn_with_no_step_at_all_is_treated_as_stale_not_as_the_awaited_one():
    inboxes = Inboxes()
    inboxes.turns.append({"sender": "thief"})
    assert reference_inbox.take_turn_at(inboxes, 1) is None


# ------------------------------------------------------------------ await_turn
def test_await_returns_as_soon_as_the_expected_turn_is_queued():
    inboxes = Inboxes()
    inboxes.turns.append(_turn(1))
    assert _run(reference_inbox.await_turn(inboxes, 1, timeout=5.0))["step"] == 1


def test_await_gives_up_rather_than_hanging_when_nothing_arrives():
    """Rule 6 charges both teams for a stall, so waiting politely is not free."""
    with pytest.raises(DeadlineExceededError, match="their turn at step 2"):
        _run(reference_inbox.await_turn(Inboxes(), 2, timeout=0.0))


def test_a_duplicate_does_not_discharge_the_deadline():
    """Liveness is not progress -- the whole point of the module."""
    inboxes = Inboxes()
    inboxes.turns.append(_turn(1))
    with pytest.raises(DeadlineExceededError):
        _run(reference_inbox.await_turn(inboxes, 2, timeout=0.0))


def test_an_audit_arriving_instead_ends_the_wait_with_their_stated_outcome():
    """Their chain is how a reference-v3 peer says it has stopped playing."""
    inboxes = Inboxes()
    inboxes.audits.append({"sender": "thief", "records": [], "result_claim": "capture"})
    with pytest.raises(OpponentFinishedError, match="capture"):
        _run(reference_inbox.await_turn(inboxes, 1, timeout=5.0))


def test_an_audit_with_no_claim_ends_the_wait_carrying_the_absence_itself():
    """Not a word standing in for one.

    Substituting "unstated" here would hand the driver a positive claim where
    the opponent made none, and it could no longer tell the two apart -- the
    exact bug :mod:`p2pchase.runtime.opponent_ending` exists to prevent.
    """
    inboxes = Inboxes()
    inboxes.audits.append({"sender": "thief", "records": []})
    with pytest.raises(OpponentFinishedError) as raised:
        _run(reference_inbox.await_turn(inboxes, 1, timeout=5.0))
    assert raised.value.args[0] == ""


def test_the_watchdog_is_fed_when_the_awaited_turn_arrives():
    inboxes = Inboxes()
    inboxes.turns.append(_turn(1))
    watchdog = Watchdog(timeout_sec=60.0)
    _run(reference_inbox.await_turn(inboxes, 1, timeout=5.0, watchdog=watchdog))
    assert watchdog.beats == 1


def test_the_watchdog_is_not_fed_by_traffic_that_makes_no_progress():
    """A peer resending step 1 forever must still trip the progress monitor."""
    inboxes = Inboxes()
    inboxes.turns.append(_turn(1))
    watchdog = Watchdog(timeout_sec=60.0)
    with pytest.raises(DeadlineExceededError):
        _run(reference_inbox.await_turn(inboxes, 2, timeout=0.0, watchdog=watchdog))
    assert watchdog.beats == 0


def test_our_own_refusal_is_surfaced_rather_than_timing_out_silently(caplog):
    """They answered; the queue is empty for a reason only this log knows."""
    inboxes = Inboxes()
    inboxes.refusals.append("timestamp: required non-empty str")
    with caplog.at_level("ERROR"), pytest.raises(DeadlineExceededError):
        _run(reference_inbox.await_turn(inboxes, 1, timeout=0.0))
    assert "timestamp: required non-empty str" in caplog.text


# ----------------------------------------------------------------- await_audit
def test_await_audit_returns_and_consumes_the_queued_chain():
    inboxes = Inboxes()
    inboxes.audits.append({"sender": "police", "records": [{"step": 1}]})
    assert _run(reference_inbox.await_audit(inboxes, timeout=5.0))["records"] == [{"step": 1}]
    assert not inboxes.audits


def test_await_audit_expires_rather_than_hanging_on_a_peer_that_has_gone():
    with pytest.raises(DeadlineExceededError, match="their audit"):
        _run(reference_inbox.await_audit(Inboxes(), timeout=0.0))
