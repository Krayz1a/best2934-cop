"""The thief's side of rule 47: not walking into the trap in the first place.

imreeyal beat us with the same three moves in all three of our thief sub-games
on 2026-08-14. Our thief ran to (6, 6) in six moves, they sealed (6, 5), and on
the one turn when a single exit remained our thief stood still -- so they sealed
(5, 6) and the sub-game was over at step 7. It then produced thirty more sealed
records of standing still and claimed survival.

:mod:`p2pchase.runtime.wall_capture` makes us *report* that correctly. This is
the half that stops it happening.

The three vetoes are tested separately because they answer to different degrees
of certainty, and the ordering matters: a cell with no exit at all loses under
the rules, a cell the cop can seal is a judgement about the opponent, and
leaving a one-exit cell is a judgement about what a wall beside us means.
"""

from __future__ import annotations

import pytest

from p2pchase.domain.own_state import OwnState
from p2pchase.domain.thief_brain import ThiefBrain

#: The corner, and the two cells imreeyal sealed behind our thief.
CORNER = (6, 6)
FIRST_WALL = (6, 5)
SECOND_WALL = (5, 6)


@pytest.fixture
def thief(thief_state) -> OwnState:
    return thief_state


def wall(state: OwnState, *cells) -> OwnState:
    for cell in cells:
        state.board.barriers.add(cell)
    return state


def moves(state: OwnState) -> list[str]:
    brain = ThiefBrain()
    return [m for m, _c in brain._survivable(state, brain._candidates(state))]


# ------------------------------------------------------------ the last exit
def test_a_thief_with_one_way_out_takes_it(thief):
    """The move that would have saved three sub-games.

    One exit means a wall has already landed beside us -- on an empty 7x7 the
    emptiest cell is a corner with two. The cop needs exactly one more.
    """
    thief.position = CORNER
    wall(thief, FIRST_WALL)

    assert "STAY" not in moves(thief)
    assert ThiefBrain()._decide_move(thief).move != "STAY"


def test_a_thief_with_room_may_still_stand_still(thief):
    """STAY is a legal and sometimes correct move. The veto is narrow."""
    thief.position = (3, 3)

    assert "STAY" in moves(thief)


def test_the_corner_itself_is_not_forbidden(thief):
    """Two exits is not a trap on its own, and refusing every edge cell would
    hand the middle of the board to the cop."""
    thief.position = (6, 5)

    assert CORNER in [cell for _m, cell in
                      ThiefBrain()._survivable(thief, ThiefBrain()._candidates(thief))]


# --------------------------------------------------------- the dead end
def test_a_cell_with_no_exit_is_never_entered(thief):
    """Moving into it loses under rule 47 whatever else it scores."""
    thief.position = (5, 6)
    wall(thief, FIRST_WALL, (5, 5))  # (6,6) now reachable only from (5,6)
    wall(thief, (4, 6))              # ...and (5,6)'s own neighbours close in

    chosen = [cell for _m, cell in
              ThiefBrain()._survivable(thief, ThiefBrain()._candidates(thief))]

    assert all(ThiefBrain()._exits(thief, cell) > 0 or cell == thief.position
               for cell in chosen)


def test_every_option_being_bad_still_returns_a_move(thief):
    """Refusing everything is not a decision. A boxed thief must still seal a
    legal step -- the concession is reported by wall_capture, not by refusing
    to play."""
    thief.position = CORNER
    wall(thief, FIRST_WALL, SECOND_WALL)

    assert moves(thief) == ["STAY"]
    assert ThiefBrain()._decide_move(thief).move == "STAY"


# ------------------------------------------------------------- trappable
def test_exits_are_counted_without_stay(thief):
    """``STAY`` is always legal, so counting it would make every cell look
    like it has a way out -- which is the reading that makes rule 47
    unsatisfiable."""
    thief.position = CORNER

    assert ThiefBrain()._exits(thief, CORNER) == 2

    wall(thief, FIRST_WALL, SECOND_WALL)

    assert ThiefBrain()._exits(thief, CORNER) == 0
