"""The discrete arena: grid, legal movement, barriers and capture detection.

Book chapter 3. Coordinates are ``(row, col)``. The origin corner and the
axis start index are negotiated (Appendix F, Table 13) but MUST be identical
on both peers -- if one side counts from 0 and the other from 1, ``[3,3]`` of
one is not ``[3,3]`` of the other and the race falls apart.

Iron rules encoded here:
  * Orthogonal movement only, one cell, or STAY. No diagonals (rules 13, 14).
  * The cop may place a barrier ONLY on a turn where it forgoes movement, and
    only on its own cell or one of the four orthogonally adjacent cells.
  * A barrier is permanent and impassable for BOTH players.
  * Placing a barrier on the cell the thief currently occupies is a capture
    (rule 46).
  * A thief with no legal move at all is likewise captured (rule 47).
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

Coord = tuple[int, int]

# Row/col deltas. Row grows downward when the origin is the top-left corner,
# so "N" (north) decreases the row index.
_DELTAS: dict[str, Coord] = {
    "N": (-1, 0),
    "S": (1, 0),
    "E": (0, 1),
    "W": (0, -1),
    "STAY": (0, 0),
}


class IllegalMoveError(ValueError):
    """Raised when a move violates the shared physics contract."""


@dataclass(frozen=True)
class BoardGeometry:
    """Immutable board shape agreed in ``config/game.json``."""

    grid_size: int
    axis_origin_corner: str = "top-left"
    axis_start_index: int = 0

    @property
    def lo(self) -> int:
        return self.axis_start_index

    @property
    def hi(self) -> int:
        return self.axis_start_index + self.grid_size - 1

    def in_bounds(self, cell: Coord) -> bool:
        r, c = cell
        return self.lo <= r <= self.hi and self.lo <= c <= self.hi

    def cells(self) -> Iterator[Coord]:
        for r in range(self.lo, self.hi + 1):
            for c in range(self.lo, self.hi + 1):
                yield (r, c)

    def delta(self, move: str) -> Coord:
        """Return the (drow, dcol) for a move name, honouring the origin corner.

        Only the vertical axis flips: with a bottom-left origin the row index
        grows upward, so "N" increases it.
        """
        if move not in _DELTAS:
            raise IllegalMoveError(
                f"{move!r} is not in the permanent move set {sorted(_DELTAS)}; "
                f"movement is orthogonal only (Appendix F, Table 15)"
            )
        dr, dc = _DELTAS[move]
        if self.axis_origin_corner in ("bottom-left", "bottom-right"):
            dr = -dr
        if self.axis_origin_corner in ("top-right", "bottom-right"):
            dc = -dc
        return (dr, dc)


@dataclass
class Board:
    """Mutable board state: barriers plus the geometry contract.

    The board deliberately does NOT hold both agents' true positions. Each peer
    owns only its own truth (book ch2, rule 8/9); the opponent's position is a
    *belief*, never a fact, until it is revealed by the protocol.
    """

    geometry: BoardGeometry
    barriers: set[Coord] = field(default_factory=set)
    max_barriers: int = 14

    # ---------------------------------------------------------------- queries
    def is_blocked(self, cell: Coord) -> bool:
        return cell in self.barriers

    def is_passable(self, cell: Coord) -> bool:
        return self.geometry.in_bounds(cell) and not self.is_blocked(cell)

    def target_of(self, origin: Coord, move: str) -> Coord:
        if move not in _DELTAS:
            raise IllegalMoveError(f"unknown move {move!r}; legal moves are {sorted(_DELTAS)}")
        dr, dc = self.geometry.delta(move)
        return (origin[0] + dr, origin[1] + dc)

    def legal_moves(self, origin: Coord) -> list[str]:
        """Legal move names from ``origin``. STAY is always legal."""
        out = []
        for move in _DELTAS:
            if move == "STAY":
                out.append(move)
                continue
            if self.is_passable(self.target_of(origin, move)):
                out.append(move)
        return out

    def has_escape(self, origin: Coord) -> bool:
        """True if at least one *movement* (not STAY) is available.

        A thief with no escape is captured (rule 47). STAY does not count as an
        escape: a thief walled in on all four sides has been caught, even
        though it could nominally stand still.
        """
        return any(m != "STAY" for m in self.legal_moves(origin))

    def barrier_targets(self, cop_cell: Coord) -> list[Coord]:
        """Cells the cop may legally turn into a barrier this turn.

        Its own cell or one of the four orthogonally adjacent cells (book ch3,
        "barrier rule"), provided the cell is in bounds and not already blocked.
        """
        if self.barriers_left <= 0:
            return []
        candidates = [cop_cell] + [
            self.target_of(cop_cell, m) for m in ("N", "S", "E", "W")
        ]
        return [c for c in candidates if self.is_passable(c)]

    @property
    def barriers_left(self) -> int:
        return self.max_barriers - len(self.barriers)

    # ---------------------------------------------------------------- mutation
    def apply_move(self, origin: Coord, move: str) -> Coord:
        """Validate and apply a movement, returning the new cell."""
        target = self.target_of(origin, move)
        if move == "STAY":
            return origin
        if not self.geometry.in_bounds(target):
            raise IllegalMoveError(f"move {move} from {origin} leaves the board")
        if self.is_blocked(target):
            raise IllegalMoveError(f"move {move} from {origin} runs into a barrier at {target}")
        return target

    def place_barrier(self, cop_cell: Coord, cell: Coord) -> None:
        """Place a barrier, enforcing quota, adjacency and permanence."""
        if self.barriers_left <= 0:
            raise IllegalMoveError(f"barrier quota exhausted ({self.max_barriers})")
        if cell not in self.barrier_targets(cop_cell):
            raise IllegalMoveError(
                f"barrier at {cell} is not within one step of the cop at {cop_cell}"
            )
        self.barriers.add(cell)

    # ---------------------------------------------------------------- helpers
    def manhattan(self, a: Coord, b: Coord) -> int:
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def shortest_path_length(self, start: Coord, goal: Coord) -> int | None:
        """Breadth-first distance honouring barriers, or None if unreachable.

        Manhattan distance ignores walls; once the cop starts building them the
        true chase distance is the BFS distance. The cop's brain uses this to
        avoid walling itself away from the thief.
        """
        if start == goal:
            return 0
        seen = {start}
        frontier = [start]
        dist = 0
        while frontier:
            dist += 1
            nxt: list[Coord] = []
            for cell in frontier:
                for move in ("N", "S", "E", "W"):
                    step = self.target_of(cell, move)
                    if step in seen or not self.is_passable(step):
                        continue
                    if step == goal:
                        return dist
                    seen.add(step)
                    nxt.append(step)
            frontier = nxt
        return None

    def reachable_area(self, start: Coord, limit: int | None = None) -> int:
        """Number of cells reachable from ``start`` (flood fill).

        The thief maximises this: shrinking free space is exactly what the cop's
        barriers are for, so "how much room do I still have" is a direct
        survival signal.
        """
        seen = {start}
        frontier = [start]
        while frontier and (limit is None or len(seen) < limit):
            nxt: list[Coord] = []
            for cell in frontier:
                for move in ("N", "S", "E", "W"):
                    step = self.target_of(cell, move)
                    if step not in seen and self.is_passable(step):
                        seen.add(step)
                        nxt.append(step)
            frontier = nxt
        return len(seen)

    def snapshot(self) -> dict:
        """Canonical, hashable view of the board (used inside commit payloads)."""
        return {
            "grid_size": self.geometry.grid_size,
            "axis_origin_corner": self.geometry.axis_origin_corner,
            "axis_start_index": self.geometry.axis_start_index,
            "barriers": sorted([list(b) for b in self.barriers]),
        }


def build_board(config: dict) -> Board:
    """Construct a Board from the shared, agreed ``game.json`` mapping."""
    ba = config.get("board_and_agents", {})
    mb = config.get("movement_and_barriers", {})
    geometry = BoardGeometry(
        grid_size=int(ba.get("grid_size", 7)),
        axis_origin_corner=str(ba.get("axis_origin_corner", "top-left")),
        axis_start_index=int(ba.get("axis_start_index", 0)),
    )
    return Board(geometry=geometry, max_barriers=int(mb.get("max_barriers", 14)))


def as_coord(value: Iterable[int]) -> Coord:
    r, c = value
    return (int(r), int(c))
