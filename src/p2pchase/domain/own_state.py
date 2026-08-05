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

from .. import constants
from .belief import BeliefMap
from .board import Board, Coord
from .scent_broadcast import DEFAULT_TRANSMIT_LAG, LaggedTrail
from .smell import ScentMap, build_scent_map
from .trail_reading import displacement_heading


@dataclass
class OwnState:
    """Everything one peer legitimately knows."""

    role: str
    board: Board
    position: Coord
    belief: BeliefMap
    my_scent: ScentMap
    opponent_scent: ScentMap
    #: The delay line that decides what the opponent may sample of our trail.
    broadcast: LaggedTrail = field(default_factory=LaggedTrail)
    step: int = 0
    #: How many of the opponent's steps we have actually seen revealed. The
    #: networked runner waits on this rather than on wall-clock time, so a peer
    #: never advances past an opponent whose message is merely slow.
    opponent_steps_seen: int = 0
    max_moves: int = constants.MAX_MOVES
    survival_threshold: int = constants.SURVIVAL_THRESHOLD
    #: Where the opponent's trail was centred when we last sampled it, and which
    #: way it moved since the sample before that. Together these are the only
    #: physical evidence we have about the opponent's heading.
    trail_centre: tuple[float, float] | None = None
    trail_drift: str | None = None
    #: The heading the opponent's latest sentence asserted, held until we have
    #: sampled the trail and can actually cross-examine it.
    pending_claim: str | None = None
    finished: bool = False
    outcome: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    tokens_used: int = 0

    # ------------------------------------------------------------------ roles
    @property
    def is_cop(self) -> bool:
        return self.role == constants.ROLE_COP

    @property
    def opponent_role(self) -> str:
        return constants.ROLE_THIEF if self.is_cop else constants.ROLE_COP

    # ---------------------------------------------------------------- actions
    def settle_move(self, move: str) -> Coord:
        """Where a committed move actually lands, given the board as it now is.

        A move is sealed a full exchange before the opponent's barrier for the
        same step is revealed -- that is what commit-reveal means -- so a choice
        that was legal when it was sealed can arrive at a cell that has just
        been walled off. The mover then stands still. This is the protocol
        working rather than a fault: the commitment seals the *choice*, so it
        still verifies at the audit, and raising here would turn an ordinary
        race between two honest peers into a technical loss for both (rule 6).

        Every other illegality -- off the board, a direction that does not exist
        -- is a fault in our own brain and still raises, because nothing in the
        protocol can cause one.
        """
        if move != "STAY" and self.board.is_blocked(self.board.target_of(self.position, move)):
            return self.position
        return self.board.apply_move(self.position, move)

    def apply_own_move(self, move: str, barrier: Coord | None = None) -> None:
        """Apply this peer's own decided action to its local truth."""
        # Snapshot before emitting: what we transmit is the trail through where
        # we *were*, never where this move puts us (I-6, see LaggedTrail).
        self.broadcast.record(self.my_scent.grid)
        if barrier is not None:
            if not self.is_cop:
                raise ValueError("only the cop may place barriers")
            if move != "STAY":
                # The barrier privilege is bought by forgoing movement.
                raise ValueError("a barrier may only be placed on a turn with no movement")
            self.board.place_barrier(self.position, barrier)
        else:
            self.position = self.settle_move(move)
        self.my_scent.emit(self.position)

    def apply_opponent_move(self, move: str, barrier: list[int] | None) -> None:
        """Fold the opponent's revealed action into our local truth.

        ``move`` is accepted and deliberately not consumed, and since I-5 it is
        usually ``""`` because a sealed move is no longer disclosed mid-game.
        Both facts are the same fact: a direction locates an agent only if you
        already know where it started, and we never know that, so this has
        always been a step counter rather than a position update. Worth stating
        outright, because it is what made sealing the move cost us nothing --
        we were disclosing ours every step and discarding theirs unread.

        Barriers, by contrast, are declared with exact coordinates (rules 15,
        16) and become hard fact.
        """
        if barrier is not None:
            cell = (int(barrier[0]), int(barrier[1]))
            self.board.barriers.add(cell)
        self.opponent_steps_seen += 1
        self.belief.predict()

    def sample_opponent_scent(self, payload: dict[str, float], merge: bool = False) -> None:
        """Load the opponent's trail and measure how far its centre has drifted.

        The drift is recorded here rather than computed on demand because the
        baseline has to advance on *every* sample, including turns where the
        opponent said nothing worth checking. Computing it lazily would compare
        against whichever turn we last happened to ask, which silently turns a
        one-turn measurement into a multi-turn one.
        """
        self.opponent_scent.load(payload, merge=merge)
        centre = self.opponent_scent.centroid()
        self.trail_drift = displacement_heading(self.trail_centre, centre)
        self.trail_centre = centre

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

    def settled_position(self, move: str, barrier: Coord | None = None) -> Coord:
        """Where an action leaves us -- the cell sealed as ``state``.

        A barrier is placed from a standstill (rule: the privilege is bought by
        forgoing movement), so it leaves the position untouched. Anything else
        settles through :meth:`settle_move`, which is what makes this the cell
        we will actually be standing on rather than the one we aimed at.
        """
        if barrier is not None:
            return self.position
        return self.settle_move(move)

    def state_digest_source(self) -> dict[str, Any]:
        """The board snapshot, for anything that still wants a state digest.

        No longer sealed into commitments -- those now carry the position
        itself, in gal-roy1's shape (see :class:`~p2pchase.domain.protocol.
        StepIntent`). Kept because the replay viewer and the log artifacts use
        it to key a board state, where a digest is the right thing.
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
    start = tuple(ba.get("cop_start" if role == constants.ROLE_COP else "thief_start", (0, 0)))
    opponent_start = tuple(ba.get("thief_start" if role == constants.ROLE_COP else "cop_start", (3, 3)))

    belief = BeliefMap(board=board)
    # Start positions are agreed in the shared config, so step 0 is certain.
    belief.reset(known_start=(int(opponent_start[0]), int(opponent_start[1])))

    my_scent = build_scent_map(config, board.geometry)
    opponent_scent = build_scent_map(config, board.geometry)
    lag = int(config.get("pheromones", {}).get(
        "pheromone_transmit_lag", DEFAULT_TRANSMIT_LAG))

    state = OwnState(
        role=role,
        board=board,
        position=(int(start[0]), int(start[1])),
        belief=belief,
        my_scent=my_scent,
        opponent_scent=opponent_scent,
        broadcast=LaggedTrail(lag=lag),
        max_moves=int(mb.get("max_moves", constants.MAX_MOVES)),
        survival_threshold=int(mb.get("survival_threshold", constants.SURVIVAL_THRESHOLD)),
    )
    state.my_scent.emit(state.position)
    # Seed the delay line with the opening emission, so a sample taken before
    # our first move answers "the field as of last turn" rather than silence.
    # It discloses nothing: both start cells are named in the agreed config and
    # the belief map is initialised from them. Leaving it empty would have made
    # the reply depend on whether the opponent sampled before or after we moved,
    # and a field that depends on call order is one the two logs disagree about.
    state.broadcast.record(state.my_scent.grid)
    return state
