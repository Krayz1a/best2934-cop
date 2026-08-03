"""One live peer's session state for a single sub-game.

This is the object the MCP server hands every incoming tool call to, and the
object the peer orchestrator drives outward through the client. Keeping both
directions in one place is deliberate: the protocol is symmetric, and splitting
"what we send" from "what we receive" would let the two halves disagree about
which step we are on.

The epistemic discipline from the local harness is preserved exactly. This
session holds our board, our position and our posterior. It never holds the
opponent's cell, because across a network nobody has it -- everything we know
about the other agent arrives as a declared barrier, a revealed direction, a
sampled scent intensity or a sentence we may or may not believe.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from ..domain.board import build_board
from ..domain.brains import BrainBase, Decision, load_brain
from ..domain.crypto import CommitRecord, audit_records, commit
from ..domain.own_state import build_own_state
from ..domain.protocol import Phase, StateMachine, StepIntent
from ..reports.artifacts import digest_payload
from ..shared.peer_config import PeerConfig
from ..strategy.talk_engine import build_talk_engine
from ..strategy.landmarks import heading_word, pick_landmark
from ..strategy.talk_prompt import TalkRequest
from .match_side import cells_matching_heading

LOGGER = logging.getLogger(__name__)


@dataclass
class PeerSession:
    """Everything one peer knows and does during one sub-game.

    Input:  a :class:`PeerConfig`, the role for this sub-game, the game id.
    Output: commitments and reveals to send; belief updates from what arrives.
    Setup:  ``seed`` makes the landmark vocabulary reproducible for replays.
    """

    config: PeerConfig
    role: str
    game_id: str
    sub_game: int = 1
    seed: int = 0
    step: int = 0
    machine: StateMachine = field(default_factory=StateMachine)
    records: list[dict[str, Any]] = field(default_factory=list)
    opponent_commitments: dict[int, str] = field(default_factory=dict)
    opponent_records: list[dict[str, Any]] = field(default_factory=list)
    lies_told: int = 0
    honest_hints: int = 0

    def __post_init__(self) -> None:
        import random

        shared = self.config.shared
        self.state = build_own_state(shared, self.role, build_board(shared))
        self.brain: BrainBase = load_brain(self.role, self.config.strategy, shared)
        self.talk = build_talk_engine(self.config.trash_talk, self.config.llm)
        self._rng = random.Random(self.seed)
        self._pending: tuple[Decision, str, CommitRecord] | None = None
        self._map_area = shared.get("world", {}).get("map_area", "")
        self._max_words = int(shared.get("world", {}).get("hint_max_words", 15))

    @property
    def group_id(self) -> str:
        return self.config.group_id

    # ------------------------------------------------------------- outbound
    def prepare_step(self, step: int) -> str:
        """Decide, seal and return the commitment for this step.

        Nothing is applied to our own board yet. A move becomes real only at
        :meth:`apply_own_step`, after the opponent has acknowledged -- so a
        message lost between COMMIT and ACK leaves both peers on the same step
        rather than one step apart.
        """
        self.step = step
        decision = self.brain.decide(self.state)
        hint = self.talk.compose(
            TalkRequest(
                role=self.role, step=step, intent=decision.intent,
                heading=heading_word(decision.move),
                landmark=pick_landmark(self._map_area, self._rng),
                max_words=self._max_words,
                steps_remaining=self.state.survival_threshold - self.state.step,
            )
        )
        intent = StepIntent(
            step=step, role=self.role, sub_game_number=self.sub_game,
            move=decision.move, hint=hint, intent=decision.intent,
            barrier=list(decision.barrier) if decision.barrier else None,
            state_digest=digest_payload(self.state.state_digest_source()),
        )
        record = commit(intent.payload())
        self._pending = (decision, hint, record)
        return record.commit

    def reveal(self) -> dict[str, Any]:
        """The disclosed view of our pending step -- nonce withheld (rule 18)."""
        if self._pending is None:
            raise RuntimeError("reveal() called before prepare_step()")
        return self._pending[2].revealed_view()

    def apply_own_step(self) -> Decision:
        """Commit the pending step to our own world and record it."""
        if self._pending is None:
            raise RuntimeError("apply_own_step() called before prepare_step()")
        decision, _hint, record = self._pending
        self.records.append(record.audit_view())
        if decision.intent == "lie":
            self.lies_told += 1
        else:
            self.honest_hints += 1
        self.state.apply_own_move(decision.move, decision.barrier)
        self._pending = None
        return decision

    # -------------------------------------------------------------- inbound
    def on_commit(self, step: int, commitment: str) -> None:
        """Record the opponent's sealed step. Nothing is knowable from it yet."""
        self.opponent_commitments[int(step)] = str(commitment)

    def on_reveal(self, step: int, move: str, hint: str,
                  barrier: list[int] | None) -> None:
        """Apply what the opponent disclosed, weighted by how much we trust it."""
        if int(step) not in self.opponent_commitments:
            raise ValueError(f"reveal for step {step} arrived without a prior commitment")
        self.state.apply_opponent_move(move, barrier)
        claimed = cells_matching_heading(self.state, move)
        honest = self.state.belief.score_hint(claimed, self.state.opponent_scent)
        self.state.belief.update_from_hint(claimed if honest else set())
        LOGGER.debug("step %d: opponent claims %s (%s); judged %s", step, move,
                     hint[:40], "credible" if honest else "doubtful")

    def scent_at(self, cells: list[list[int]]) -> dict[str, float]:
        """Our own pheromone intensity at the cells the opponent asked about."""
        return {
            f"{int(c[0])},{int(c[1])}": self.state.my_scent.intensity((int(c[0]), int(c[1])))
            for c in cells
        }

    def absorb_scent(self, samples: dict[str, float]) -> None:
        """Fold sampled opponent intensities into our posterior.

        Merged rather than replaced: over the network we sample only the cells
        we asked about, so a replace would throw away every earlier reading.
        """
        self.state.opponent_scent.load(samples, merge=True)
        self.state.belief.update_from_scent(self.state.opponent_scent)

    # ------------------------------------------------------------ finishing
    def end_of_turn(self) -> None:
        self.state.end_of_full_turn()

    def final_reveal(self) -> list[dict[str, Any]]:
        """Our complete audit view, nonces included, once the sub-game is over."""
        self.machine.phase = Phase.FINALISING
        return list(self.records)

    def audit(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Verify the opponent's disclosed chain (rules 19, 36)."""
        self.opponent_records = list(records)
        return audit_records(records).as_dict()
