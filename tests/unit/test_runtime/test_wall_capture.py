"""Rule 46 from the thief's side: conceding when walled (I-8, rules 35, 46).

Reported by gal-roy1 on 2026-08-09 with our own sealed records as the evidence.
Their cop dropped a barrier on the cell our thief's committed record puts it on,
twice per sub-game across three sub-games, and our thief never conceded --
because ``i_am_caught`` was only ever set by an explicit ``capture_claim``, and
nothing obliges a cop to send one. All three were scored SURVIVAL. About forty
five points, and worse than the points: two peers filing different outcomes for
one sub-game is what rule 35 voids for both teams.

The test that matters here is the *second* one. Conceding whenever a wall
touches us would be the easy fix and it would file captures gal-roy1 does not
record, which is the same disagreement from the other side.
"""

from __future__ import annotations

import pytest

from p2pchase import constants
from p2pchase.runtime import wall_capture
from p2pchase.runtime.peer_session import PeerSession
from p2pchase.runtime.turn_loop import TurnLoop


@pytest.fixture
def thief(thief_config) -> PeerSession:
    return PeerSession(thief_config, constants.ROLE_THIEF, "g", seed=6)


@pytest.fixture
def cop(peer_config) -> PeerSession:
    return PeerSession(peer_config, constants.ROLE_COP, "g", seed=6)


def here(session) -> list[int]:
    return [int(session.state.position[0]), int(session.state.position[1])]


# ------------------------------------------------------------------ entering
def test_a_wall_on_our_cell_is_watched(thief):
    assert wall_capture.entering(thief, here(thief)) == tuple(here(thief))


def test_a_wall_somewhere_else_is_not(thief):
    x, y = here(thief)
    assert wall_capture.entering(thief, [x + 2, y + 2]) is None


def test_a_turn_that_placed_no_barrier_is_not(thief):
    assert wall_capture.entering(thief, None) is None


@pytest.mark.parametrize("junk", ["6,6", [6], [6, 6, 6], ["a", "b"], 6])
def test_a_barrier_that_is_not_a_coordinate_is_ignored(thief, junk):
    """Over the wire this field is whatever the opponent sent. A crash here is a
    transport failure to them and rule 6 charges the stall to both teams."""
    assert wall_capture.entering(thief, junk) is None


def test_the_cop_is_never_captured_by_a_barrier(cop):
    """Rule 46 names the thief. A cop that conceded to its own wall would hand
    the sub-game away on a move it is entitled to make."""
    assert wall_capture.entering(cop, here(cop)) is None


# ------------------------------------------------------------------- leaving
def test_still_on_the_wall_at_the_end_of_the_round_is_a_capture(thief):
    wall = wall_capture.entering(thief, here(thief))
    assert wall_capture.leaving(thief, wall) is True
    assert thief.i_am_caught is True


def test_stepping_off_the_wall_is_not_conceded(thief):
    """The case I-8(a) has not settled, and the reason this check is narrow.
    gal-roy1's own post-audit checker stays quiet about a thief that moved
    within the round, so ours does too -- matching their test is what keeps our
    two reports agreeing, which is worth more than the stricter reading."""
    wall = wall_capture.entering(thief, here(thief))
    x, y = wall
    thief.state.position = (x + 1, y)
    assert wall_capture.leaving(thief, wall) is False
    assert thief.i_am_caught is False


def test_nothing_watched_means_nothing_conceded(thief):
    assert wall_capture.leaving(thief, None) is False
    assert thief.i_am_caught is False


# ------------------------------------------------- through the whole round
def test_taking_a_turn_ends_the_sub_game_when_the_wall_has_us(thief, monkeypatch):
    """The wiring, which no test of the helper alone can reach: ``take_turn``
    must consult rule 46 *after* applying our move and end the sub-game. This is
    the step that was missing -- gal-roy1's thief kept playing 22 more steps
    after being walled at step 13 and filed the result as a survival."""
    monkeypatch.setattr(wall_capture, "leaving", lambda *_a: True)
    loop = TurnLoop(thief)
    loop.walled = (0, 0)
    loop.take_turn(1)
    assert loop.finished == constants.OUTCOME_CAPTURE
    assert loop.walled is None


def test_taking_a_turn_leaves_an_unwalled_thief_playing(thief, monkeypatch):
    """The other half, and the one that protects the ordinary game: a round in
    which no wall has us must not end anything."""
    monkeypatch.setattr(wall_capture, "leaving", lambda *_a: False)
    loop = TurnLoop(thief)
    loop.take_turn(1)
    assert loop.finished == ""
