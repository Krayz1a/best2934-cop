"""The knock deadline, and why it is bounded but not fixed.

``_await_opponent`` gives up after two minutes because rule 6 charges *both*
teams for a sub-game that never starts, so at some point not-playing has to be
a decision rather than a hang. That reasoning assumes a match at an agreed T.

It broke the first time we tried the other shape. We told imreeyal "any hour,
including now -- just dial in", started the driver, and it exited 120 seconds
later while their peer was still unbound. An open standby needs a bound
measured in hours; a scheduled match still wants two minutes. So the bound is
configurable rather than removed, and a bad value must never be the reason a
sub-game is forfeited.
"""

from __future__ import annotations

import pytest

from p2pchase.runtime import peer_host


@pytest.fixture(autouse=True)
def _clear(monkeypatch):
    monkeypatch.delenv(peer_host.OPPONENT_WAIT_ENV, raising=False)


def test_the_default_is_two_minutes_when_nothing_is_set():
    assert peer_host.opponent_wait_sec() == peer_host.OPPONENT_WAIT_SEC


def test_an_open_standby_can_ask_for_hours(monkeypatch):
    monkeypatch.setenv(peer_host.OPPONENT_WAIT_ENV, "28800")
    assert peer_host.opponent_wait_sec() == 28800.0


def test_a_fractional_value_is_honoured(monkeypatch):
    monkeypatch.setenv(peer_host.OPPONENT_WAIT_ENV, "0.5")
    assert peer_host.opponent_wait_sec() == 0.5


@pytest.mark.parametrize("bad", ["", "   ", "soon", "12s", "nan-ish", "-1", "0"])
def test_a_bad_value_falls_back_rather_than_raising(monkeypatch, bad):
    """A mistyped shell variable must not forfeit the sub-game.

    Raising here would fail the match at the one moment nobody is watching the
    terminal, and rule 6 charges both teams for that -- a strictly worse
    outcome than waiting the default.
    """
    monkeypatch.setenv(peer_host.OPPONENT_WAIT_ENV, bad)
    assert peer_host.opponent_wait_sec() == peer_host.OPPONENT_WAIT_SEC


def test_a_bad_value_says_so_in_the_log(monkeypatch, caplog):
    """Falling back silently would hide a two-minute wait the operator did not want."""
    monkeypatch.setenv(peer_host.OPPONENT_WAIT_ENV, "soon")
    with caplog.at_level("WARNING"):
        peer_host.opponent_wait_sec()
    assert peer_host.OPPONENT_WAIT_ENV in caplog.text


def test_an_explicit_argument_still_wins_over_the_environment(monkeypatch):
    """Callers that pass a timeout mean it; the env is only the default."""
    monkeypatch.setenv(peer_host.OPPONENT_WAIT_ENV, "28800")
    import inspect
    assert inspect.signature(
        peer_host._await_opponent).parameters["timeout"].default is None
