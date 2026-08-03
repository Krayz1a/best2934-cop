"""Board geometry, legal movement and the barrier rule (book ch3)."""

from __future__ import annotations

import pytest

from p2pchase.domain.board import (
    Board,
    IllegalMoveError,
    as_coord,
    build_board,
)


def test_geometry_bounds(geometry):
    assert geometry.in_bounds((0, 0))
    assert geometry.in_bounds((6, 6))
    assert not geometry.in_bounds((-1, 0))
    assert not geometry.in_bounds((7, 0))
    assert len(list(geometry.cells())) == 49


def test_delta_rejects_diagonal_moves(geometry):
    """Rule: movement is orthogonal only. A diagonal is not a slow bug, it is illegal."""
    for move in ("N", "S", "E", "W", "STAY"):
        assert geometry.delta(move) is not None
    with pytest.raises(IllegalMoveError):
        geometry.delta("NE")


def test_legal_moves_at_a_corner(board):
    moves = board.legal_moves((0, 0))
    assert set(moves) >= {"S", "E", "STAY"}
    assert "N" not in moves
    assert "W" not in moves


def test_move_into_a_barrier_is_refused(board):
    board.barriers.add((0, 1))
    assert "E" not in board.legal_moves((0, 0))
    with pytest.raises(IllegalMoveError):
        board.apply_move((0, 0), "E")


def test_stay_does_not_count_as_an_escape(board):
    """Rule 47: a thief whose only option is STAY is boxed in, hence captured."""
    board.barriers.update({(0, 1), (1, 0)})
    assert board.legal_moves((0, 0)) == ["STAY"]
    assert not board.has_escape((0, 0))


def test_barrier_targets_are_self_or_orthogonal_neighbours(board):
    targets = set(board.barrier_targets((3, 3)))
    assert targets == {(3, 3), (2, 3), (4, 3), (3, 2), (3, 4)}


def test_barrier_placement_is_bounded_by_range_and_quota(board):
    board.place_barrier((3, 3), (3, 4))
    assert (3, 4) in board.barriers
    with pytest.raises(IllegalMoveError):
        board.place_barrier((3, 3), (0, 0))  # two steps away


def test_a_barrier_is_permanent(board):
    board.place_barrier((3, 3), (3, 4))
    with pytest.raises(IllegalMoveError):
        board.place_barrier((3, 3), (3, 4))  # already sealed


def test_quota_is_enforced(shared_config):
    small = {**shared_config,
             "movement_and_barriers": {**shared_config["movement_and_barriers"],
                                       "max_barriers": 1}}
    board = build_board(small)
    board.place_barrier((3, 3), (3, 4))
    assert board.barriers_left == 0
    with pytest.raises(IllegalMoveError):
        board.place_barrier((3, 3), (2, 3))


def test_shortest_path_respects_barriers(geometry):
    board = Board(geometry=geometry)
    assert board.shortest_path_length((0, 0), (0, 2)) == 2
    # Sealing (0,1) and (1,1) forces a detour down and around through row 2.
    board.barriers.update({(0, 1), (1, 1)})
    assert board.shortest_path_length((0, 0), (0, 2)) == 6


def test_shortest_path_returns_none_when_walled_off(geometry):
    board = Board(geometry=geometry)
    board.barriers.update({(0, 1), (1, 0)})
    assert board.shortest_path_length((0, 0), (6, 6)) is None


def test_reachable_area_shrinks_as_walls_go_up(board):
    before = board.reachable_area((3, 3))
    board.barriers.update({(0, 1), (1, 0)})
    after = board.reachable_area((3, 3))
    assert after == before - 3  # the two walls plus the cell they seal off


def test_reachable_area_honours_its_limit(board):
    assert board.reachable_area((3, 3), limit=5) == 5


def test_snapshot_is_stable_and_ordered(board):
    board.barriers.update({(2, 2), (1, 1)})
    assert board.snapshot() == board.snapshot()
    assert board.snapshot()["barriers"] == [[1, 1], [2, 2]]


def test_as_coord_normalises_any_pair():
    assert as_coord([2, 3]) == (2, 3)
    assert as_coord((2, 3)) == (2, 3)
