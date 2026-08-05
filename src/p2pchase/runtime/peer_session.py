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

from .. import constants
from ..domain.audit import audit_against_commitments
from ..domain.board import build_board
from ..domain.brains import BrainBase, Decision, load_brain
from ..domain.crypto import CommitRecord, commit
from ..domain.own_state import build_own_state
from ..domain.protocol import Phase, StateMachine, StepIntent
from ..reports.artifacts import digest_payload
from ..shared.peer_config import PeerConfig
from ..strategy.landmarks import heading_word, pick_landmark
from ..strategy.talk_engine import build_talk_engine
from ..strategy.talk_prompt import TalkRequest
from .match_side import judge_claim, record_claim

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
    #: Set when we answered a cop's capture claim truthfully in the affirmative.
    i_am_caught: bool = False
    #: How the opponent said the sub-game ended, once their final reveal arrives.
    opponent_finished: str = ""
    #: The verdict on the opponent's chain, whichever way round it reached us.
    last_audit: dict[str, Any] = field(default_factory=dict)

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
                heading=heading_word(decision.spoken_heading),
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
        """The disclosed view of our pending step.

        Nonce withheld (rule 18), and since I-5 the move, the truth/lie flag and
        the state digest with it -- see
        :data:`~p2pchase.domain.crypto.MID_GAME_FIELDS`.
        """
        if self._pending is None:
            raise RuntimeError("reveal() called before prepare_step()")
        return self._pending[2].revealed_view()

    def pending_cell(self) -> tuple[int, int] | None:
        """Where our pending move puts us -- or the cell we are about to seal.

        The reveal is sent *before* the step is applied, so our own attribute
        still holds the previous cell. Comparing pre-move cells would report a
        capture whenever the two agents swapped places, which is not one.
        """
        if self._pending is None:
            return None
        decision = self._pending[0]
        if decision.barrier:
            return (int(decision.barrier[0]), int(decision.barrier[1]))
        cell = self.state.settle_move(decision.move)
        return (int(cell[0]), int(cell[1]))

    def capture_claim(self) -> list[int] | None:
        """The cell we assert the thief occupies, if we are the cop.

        A cop cannot see the thief, so it claims the only cell it can speak for
        honestly: its own, after moving -- or the cell it just sealed, since a
        barrier dropped on the thief is also a capture (rule 46). The thief
        answers truthfully because the sealed record settles it either way at
        the audit, and a false answer forfeits the game (rule 22).
        """
        if self.role != constants.ROLE_COP:
            return None
        cell = self.pending_cell()
        return None if cell is None else [cell[0], cell[1]]

    def answer_capture_claim(self, cell: list[int] | None) -> bool | None:
        """Truthfully answer the cop's claim (rules 21, 22). ``None`` if none made."""
        if cell is None:
            return None
        mine = self.pending_cell() or self.state.position
        caught = (int(cell[0]), int(cell[1])) == (int(mine[0]), int(mine[1]))
        if caught:
            self.i_am_caught = True
        return caught

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

    def on_opponent_finished(self, outcome: str) -> None:
        """Note that the opponent has ended the sub-game, and how they say it ended.

        Recorded rather than acted on: the runner decides what to do about it,
        and a peer that stopped early still owes us a chain that has to audit.
        """
        self.opponent_finished = outcome or constants.OUTCOME_SURVIVAL
        LOGGER.info("the opponent has ended sub-game %d: %s", self.sub_game, outcome or "unstated")

    def on_reveal(self, step: int, move: str, hint: str,
                  barrier: list[int] | None,
                  capture_claim: list[int] | None = None) -> bool | None:
        """Apply what the opponent disclosed, weighted by how much we trust it."""
        if int(step) not in self.opponent_commitments:
            raise ValueError(f"reveal for step {step} arrived without a prior commitment")
        self.state.apply_opponent_move(move, barrier)
        # Since I-5 ``move`` is normally "" -- neither peer discloses one until
        # the audit. That costs us nothing, because the hint was always the only
        # thing worth judging: the move is sealed in the commitment and so
        # cannot lie, and cross-examining a statement that cannot lie would
        # confirm honesty every time and pin the trust estimator at its ceiling.
        # So it is the sentence that gets judged, and only once we have sampled
        # the trail it has to agree with, which happens in :meth:`absorb_scent`.
        claim = record_claim(self.state, hint)
        LOGGER.debug("step %d: opponent moved %s and claims %s (%r)",
                     step, move, claim or "nothing", hint[:40])
        return self.answer_capture_claim(capture_claim)

    def scent_at(self, cells: list[list[int]]) -> dict[str, float]:
        """Our own pheromone intensity at the cells the opponent asked about."""
        return {
            f"{int(c[0])},{int(c[1])}": self.state.my_scent.intensity((int(c[0]), int(c[1])))
            for c in cells
        }

    def absorb_scent(self, samples: dict[str, float]) -> None:
        """Fold sampled opponent intensities into our posterior, then judge.

        Merged rather than replaced: over the network we sample only the cells
        we asked about, so a replace would throw away every earlier reading.

        Settling the standing verbal claim here keeps the networked path
        identical to the local harness -- the trail is what a claim is checked
        against, so this is the first moment the check is possible.
        """
        self.state.sample_opponent_scent(samples, merge=True)
        self.state.belief.update_from_scent(self.state.opponent_scent)
        honest = judge_claim(self.state)
        LOGGER.debug("claim judged %s; trust now %.3f",
                     {True: "credible", False: "doubtful"}.get(honest, "unreadable"),
                     self.state.belief.trust)

    # ------------------------------------------------------------ finishing
    def end_of_turn(self) -> None:
        self.state.end_of_full_turn()

    def final_reveal(self) -> list[dict[str, Any]]:
        """Our complete audit view, nonces included, once the sub-game is over.

        Includes the *pending* step, if the sub-game ended between our
        commitment going out and the step being applied. That happens on nearly
        every capture: the winning claim is answered inside the loser's server,
        the loser exits, and the winner's own step never completes -- so the
        opponent holds a commitment for a step we would otherwise never
        disclose.

        Withholding it is not an option, however innocent the cause. An auditor
        that cross-checks live commitments reads the gap as concealment, and it
        is right to: "the last step need not be disclosed" is precisely the
        loophole worth exploiting -- commit, see how the round turned out, then
        stay silent about it. The payload was sealed before the outcome was
        known, so disclosing it costs nothing and proves that.
        """
        self.machine.phase = Phase.FINALISING
        disclosed = list(self.records)
        if self._pending is not None:
            disclosed.append(self._pending[2].audit_view())
        return disclosed

    def audit(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Verify the opponent's disclosed chain (rules 19, 36).

        Cross-checked against ``opponent_commitments`` -- the seals that arrived
        during play -- and not merely against the ``commit`` each disclosed
        record carries about itself. Self-consistency is free to forge: rewrite
        the payload, keep the nonce, recompute the hash, and the record verifies
        against its own new seal. What a forger cannot change is what we were
        handed at the time.

        The verdict is kept because the chain can arrive either way round: we
        ask for it, or they push it when they stop first. The second case
        happens exactly when they have gone, so there is nobody left to ask.
        """
        self.opponent_records = list(records)
        self.last_audit = audit_against_commitments(
            records, dict(self.opponent_commitments)).as_dict()
        return self.last_audit
