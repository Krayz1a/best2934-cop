"""Classifying failures and backing off correctly (book ch9.3.3)."""

from __future__ import annotations

import pytest

from p2pchase.infra.retrying import (
    RetryPolicy,
    is_rate_limited,
    is_transient,
    status_of,
)


class StatusCodeError(Exception):
    status_code = 503


class ResponseAttrError(Exception):
    class _Response:
        status_code = 429

    response = _Response()


def test_status_is_read_from_whichever_attribute_the_library_used():
    assert status_of(StatusCodeError()) == 503
    assert status_of(ResponseAttrError()) == 429


def test_status_falls_back_to_scanning_the_message():
    assert status_of(RuntimeError("server said 429 Too Many Requests")) == 429


def test_an_unclassifiable_error_has_no_status():
    assert status_of(ValueError("nope")) is None


def test_rate_limits_and_server_faults_are_worth_retrying():
    assert is_transient(StatusCodeError())
    assert is_transient(ResponseAttrError())
    assert is_transient(TimeoutError())
    assert is_transient(ConnectionError())


def test_a_permanent_failure_is_not_worth_retrying():
    """Retrying a 401 fails identically every time while burning quota."""
    assert not is_transient(RuntimeError("401 Unauthorized"))
    assert not is_transient(ValueError("malformed request"))


def test_only_a_429_is_rate_limiting():
    assert is_rate_limited(ResponseAttrError())
    assert not is_rate_limited(StatusCodeError())


def test_backoff_grows_exponentially():
    policy = RetryPolicy(backoff_sec=2.0, multiplier=3.0)
    assert policy.delay_for(1) == pytest.approx(2.0)
    assert policy.delay_for(2) == pytest.approx(6.0)
    assert policy.delay_for(3) == pytest.approx(18.0)


def test_a_call_that_succeeds_immediately_reports_one_attempt():
    policy = RetryPolicy(sleep=lambda _s: None)
    result, attempts = policy.run(lambda: "ok")
    assert (result, attempts) == ("ok", 1)


def test_arguments_are_forwarded():
    policy = RetryPolicy(sleep=lambda _s: None)
    result, _ = policy.run(lambda a, b: a * b, (3,), {"b": 4})
    assert result == 12


def test_it_gives_up_after_the_attempt_ceiling():
    attempts = {"n": 0}

    def always_503():
        attempts["n"] += 1
        raise StatusCodeError()

    policy = RetryPolicy(max_retries=2, backoff_sec=0.0, sleep=lambda _s: None)
    with pytest.raises(StatusCodeError):
        policy.run(always_503)
    assert attempts["n"] == 3  # the first try plus two retries


def test_a_429_hook_overrides_the_normal_backoff():
    """The server's own signal outranks our schedule."""
    slept: list[float] = []
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ResponseAttrError()
        return "ok"

    policy = RetryPolicy(max_retries=2, backoff_sec=1.0, sleep=slept.append)
    result, _ = policy.run(flaky, on_rate_limit=lambda: 30.0)
    assert result == "ok"
    assert slept == [30.0]
