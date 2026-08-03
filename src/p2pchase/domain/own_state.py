"""One peer's LOCAL truth -- the only world state it is entitled to hold.

Book chapter 2 and rules 8/9. A peer knows, with certainty:
  * where it itself stands,
  * every barrier declared openly on the network (the cop must declare each
    placement truthfully, rule 15/16, so barriers are common knowledge),
  * its own emitted scent field and the opponent's sampled field,
  * whatever the opponent has revealed through the protocol.

It does NOT know where the opponent actually is. That is a *belief*, and the
separation is enforced here structurally: there is no attribute on this class
holding the opponent's true cell. Rendering or reasoning over an objective full
board view would be an illegal information advantage and disqualifies the
project.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .. import constants as K
from .belief import BeliefMap
from .board import Board, Coord
from .smell import ScentMap, build_scent_map


@dataclass
class OwnState:
    """Everything one peer legitimately knows."""

    role: str
    board: Board
    position: Coord
    belief: BeliefMap
    my_scent: ScentMap
    opponent_scent: ScentMap
    step: int = 0
    max_moves: int = K.MAX_MOVES
    survival_threshold: int = K.SURVIVAL_THRESHOLD
    finished: bool = False
    outcome: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0

    # ------------------------------------------------------------------ roles
    @property
    def is_cop(self) -> bool:
        return self.role == K.ROLE_COP

    @property
    def opponent_role(self) -> str:
        return K.ROLE_THIEF if self.is_cop else K.ROLE_COP

    # ---------------------------------------------------------------- actions
    def apply_own_move(self, move: str, barrier: Coord | None = None) -> None:
        """Apply this peer's own decided action to its local truth."""
        if barrier is not None:
            if not self.is_cop:
                raise ValueError("only the cop may place barriers")
            if move != "STAY":
                # The barrier privilege is bought by forgoing movement.
                raise ValueError("a barrier may only be placed on a turn with no movement")
            self.board.place_barrier(self.position, barrier)
        else:
            self.position = self.board.apply_move(self.position, move)
        self.my_scent.emit(self.position)

    def apply_opponent_move(self, move: str, barrier: list[int] | None) -> None:
        """Fold the opponent's revealed action into our local truth.

        We learn the *action*, not the position: a move name only tells us where
        they went if we already knew where they were. Barriers, by contrast, are
        declared with exact coordinates and become hard fact.
        """
        if barrier is not None:
            cell = (int(barrier[0]), int(barrier[1]))
            self.board.barriers.add(cell)
        self.belief.predict()

    def sample_opponent_scent(self, payload: dict[str, float]) -> None:
        """Load the opponent's trail as sampled from the board this turn."""
        self.opponent_scent.load(payload)

    def end_of_full_turn(self) -> None:
        """Decay every trail once both agents have moved (book ch4.3)."""
        self.my_scent.decay_all()
        self.opponent_scent.decay_all()
        self.step += 1

    # -------------------------------------------------------------- terminal
    def capture_check(self, opponent_cell: Coord | None) -> bool:
        """True if the cop has captured, given a disclosed opponent cell."""
        if not self.is_cop or opponent_cell is None:
            return False
        return self.position == opponent_cell

    def thief_is_boxed_in(self) -> bool:
        """Rule 47: a thief with no legal move at all counts as captured."""
        if self.is_cop:
            return False
        return not self.board.has_escape(self.position)

    def survival_reached(self) -> bool:
        return self.step >= self.survival_threshold

    def moves_exhausted(self) -> bool:
        return self.step >= self.max_moves

    # ---------------------------------------------------------------- exports
    def local_view(self) -> dict[str, Any]:
        """Serialisable LOCAL view -- what the live GUI is allowed to render."""
        return {
            "role": self.role,
            "step": self.step,
            "my_position": list(self.position),
            "barriers": sorted([list(b) for b in self.board.barriers]),
            "barriers_left": self.board.barriers_left,
            "belief": self.belief.as_dict(),
            "belief_top": [[list(c), round(p, 4)] for c, p in self.belief.top(5)],
            "belief_entropy": round(self.belief.entropy(), 4),
            "hint_trust": round(self.belief.trust, 4),
            "opponent_scent": self.opponent_scent.as_dict(),
            "my_scent": self.my_scent.as_dict(),
            "tokens_used": self.tokens_used,
            "finished": self.finished,
            "outcome": self.outcome,
        }

    def state_digest_source(self) -> dict[str, Any]:
        """The board snapshot sealed into each commitment.

        Binding the commitment to a state snapshot is what stops an old
        commitment being replayed in a new context (book ch5.3.1).
        """
        return {
            "step": self.step,
            "role": self.role,
            "position": list(self.position),
            "board": self.board.snapshot(),
        }


def build_own_state(config: dict, role: str, board: Board) -> OwnState:
    """Assemble a peer's starting local truth from the agreed config."""
    ba = config.get("board_and_agents", {})
    mb = config.get("movement_and_barriers", {})
    start = tuple(ba.get("cop_start" if role == K.ROLE_COP else "thief_start", (0, 0)))
    opponent_start = tuple(ba.get("thief_start" if role == K.ROLE_COP else "cop_start", (3, 3)))

    belief = BeliefMap(board=board)
    # Start positions are agreed in the shared config, so step 0 is certain.
    belief.reset(known_start=(int(opponent_start[0]), int(opponent_start[1])))

    my_scent = build_scent_map(config, board.geometry)
    opponent_scent = build_scent_map(config, board.geometry)

    state = OwnState(
        role=role,
        board=board,
        position=(int(start[0]), int(start[1])),
        belief=belief,
        my_scent=my_scent,
        opponent_scent=opponent_scent,
        max_moves=int(mb.get("max_moves", K.MAX_MOVES)),
        survival_threshold=int(mb.get("survival_threshold", K.SURVIVAL_THRESHOLD)),
    )
    state.my_scent.emit(state.position)
    return state
