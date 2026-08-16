"""The thief's half of the parking bug, and the flag that reverts it.

Our cop steered on a belief-weighted expectation that goes flat and froze on
(3, 3). Our thief had the same disease in the opposite role and we did not see
it for longer, because a frozen thief still *reports* survival.

The arithmetic: the shipped weights were ``idle_penalty`` 1.0 against
``distance_weight`` 1.2. On the far wall every legal move steps one closer to
the believed cop and loses 1.2, while standing still loses only 1.0. So STAY
wins by construction -- at every entropy, from the moment the thief reaches the
farthest non-trappable cell, for the rest of the sub-game.

It showed on the wire as 30 of 35 steps stationary against anrbj666, 25 of 35
against gal-roy1, 30 of 36 against imreeyal: three independent opponents, the
same freeze, always pinned to an edge.

What makes it fatal rather than merely passive is ``pheromone_transmit_lag``.
The field we transmit is one turn stale, so it names the cell we were in last
turn -- but a thief that did not move is still in that cell. Staying converts a
stale trail into a live one, and :mod:`p2pchase.domain.trail_inversion` shows
the book model's trail is exactly invertible (0 violations over 264 measured
transitions). We were handing our exact current cell to any opponent who
bothered to fit the kernel.
"""

from __future__ import annotations

import pytest

from p2pchase.domain.board import build_board
from p2pchase.domain.brains import load_brain
from p2pchase.domain.own_state import build_own_state
from p2pchase.domain.thief_brain import ThiefBrain

STEPS = 35


def _walk(shared: dict, roaming: bool) -> list[tuple[int, int]]:
    """Drive a whole sub-game and return the cells we stood on.

    The brain is built through ``load_brain`` with the strategy dict, which is
    exactly what ``peer_session`` does. Constructing ``ThiefBrain()`` directly
    would leave ``tuning`` empty and quietly test the flag as always-off --
    the same way ``track_deposit`` passed every test while being unreachable.
    """
    strategy = {"roam_when_blind": roaming}
    board = build_board(shared)
    state = build_own_state(shared, "thief", board, "multiplicative_book_v1", strategy)
    brain = load_brain("thief", strategy, shared)
    path = [state.position]
    for step in range(1, STEPS + 1):
        state.step = step
        move = brain.decide(state).move
        state.position = state.board.target_of(state.position, move)
        path.append(state.position)
        state.apply_opponent_move("", None)
    return path


def _still(path: list[tuple[int, int]]) -> int:
    return sum(1 for before, after in zip(path, path[1:], strict=False) if before == after)


@pytest.fixture
def shared(shared_config) -> dict:
    return shared_config


# ------------------------------------------------------------------ the bug
def test_the_shipped_thief_freezes(shared):
    """Characterisation. Delete this when the flag stops being revertible."""
    path = _walk(shared, roaming=False)

    assert _still(path) >= 25
    assert len(set(path)) <= 8


def test_roaming_never_stands_still(shared):
    """Standing still is only justified by information, and a thief has none."""
    assert _still(_walk(shared, roaming=True)) == 0


def test_roaming_uses_the_board(shared):
    """Not-parked is not enough: without memory it paces between two cells.

    A two-cycle narrows a pursuer's search from one cell to two, which is an
    improvement worth almost nothing -- hence ``_remember``.
    """
    parked = set(_walk(shared, roaming=False))
    roaming = set(_walk(shared, roaming=True))

    assert len(roaming) >= 2 * len(parked)


def test_roaming_comes_off_the_wall(shared):
    """Edges have three ways out and corners two; the middle has four."""

    def on_edge(path):
        size = 7
        return sum(1 for r, c in path if r in (0, size - 1) or c in (0, size - 1))

    assert on_edge(_walk(shared, roaming=True)) < on_edge(_walk(shared, roaming=False)) / 2


# ------------------------------------------------------- the flag itself
def test_the_flag_is_off_by_default(shared):
    """An absent key must leave the shipped behaviour exactly as it was."""
    board = build_board(shared)
    state = build_own_state(shared, "thief", board, "multiplicative_book_v1", {})

    assert ThiefBrain({}, {})._roams() is False
    assert ThiefBrain({}, {})._idle_cost(1.2) == pytest.approx(ThiefBrain.IDLE_PENALTY)
    assert state.position == (3, 3)


def test_arming_makes_stillness_cost_more_than_a_step(shared):
    """The inequality that was the whole bug, pinned in both directions."""
    armed = ThiefBrain({}, {"roam_when_blind": True})

    assert armed._idle_cost(1.2) > 1.2
    assert armed._idle_cost(2.0) > 2.0


def test_a_tuned_idle_penalty_still_wins_when_it_is_larger(shared):
    """Arming raises the floor; it must not lower a weight someone chose."""
    armed = ThiefBrain({}, {"roam_when_blind": True, "idle_penalty": 99.0})

    assert armed._idle_cost(1.2) == pytest.approx(99.0)


# ------------------------------------------------------------- blindness
def test_a_fresh_belief_is_not_blind(shared):
    """At step 1 the belief is sharp and correct: the cop really is in a corner.

    Measured against the board rather than the belief's own support, which is
    still growing early and would read 0.96 here.
    """
    board = build_board(shared)
    state = build_own_state(shared, "thief", board, "multiplicative_book_v1", {})

    assert ThiefBrain({}, {})._blind(state) is False


def test_a_diffused_belief_is_blind(shared):
    """After a full sub-game of prediction with no update, it is noise."""
    board = build_board(shared)
    state = build_own_state(shared, "thief", board, "multiplicative_book_v1", {})
    for _ in range(STEPS):
        state.apply_opponent_move("", None)

    assert ThiefBrain({}, {})._blind(state) is True
