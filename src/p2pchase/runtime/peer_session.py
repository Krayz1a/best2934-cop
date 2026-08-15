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
from ..domain.board import build_board
from ..domain.brains import BrainBase, Decision, load_brain
from ..domain.crypto import CommitRecord, commit
from ..domain.own_state import build_own_state
from ..domain.protocol import StateMachine, StepIntent
from ..reports.naming import opponent_in_game_id
from ..shared.peer_config import PeerConfig
from ..strategy.landmarks import heading_word, pick_landmark
from ..strategy.talk_engine import build_talk_engine
from ..strategy.talk_prompt import TalkRequest
from . import belief_probe
from . import session_disclosure as disclosure
from .match_side import judge_claim, record_claim
from .opponent_ending import record_ending

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
    #: Every distinct ``sub_game_number`` an opponent has declared to this
    #: session, in arrival order. Ours is :attr:`sub_game`; this is theirs, and
    #: the two disagreeing is the fact a settlement needs and cannot recover
    #: later. Kept even when it matches, because "they agreed" is evidence too.
    declared_sub_games: list[int] = field(default_factory=list)
    #: The key names each opening payload actually carried, in arrival order.
    #:
    #: Because :attr:`declared_sub_games` records our *parse* and not their
    #: *arrival*: the extractor reads ``payload.get("sub_game_number", 0)``, so
    #: a missing key and a declared ``0`` both land as ``0``. On 2026-08-16 the
    #: gal-roy1 throwaway logged ``[0]`` and we could not say whether they sent
    #: 0, sent nothing, or sent it under a spelling we do not read -- the exact
    #: ambiguity the field was added to remove. The keys settle it.
    declaration_keys: list[list[str]] = field(default_factory=list)
    seed: int = 0
    step: int = 0
    #: Who we are playing, which selects the per-pair terms (scent model, role
    #: convention). Left empty it is read off ``game_id``, whose form is
    #: ``sorted(a, b)`` joined by ``-vs-`` and therefore already carries it.
    opponent: str = ""
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
        self.opponent = self.opponent or opponent_in_game_id(self.game_id, self.config.group_id)
        self.state = build_own_state(shared, self.role, build_board(shared),
                                     self.config.scent_model(self.opponent))
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
            position=self.state.settled_position(decision.move, decision.barrier),
        )
        record = commit(intent.payload(), form=self.config.seal_form(self.opponent))
        self._pending = (decision, hint, record)
        return record.commit

    def reveal(self) -> dict[str, Any]:
        """The disclosed view of our pending step.

        Nonce withheld (rule 18), and since I-5 the move, the truth/lie flag and
        the sealed position with it -- see
        :data:`~p2pchase.domain.crypto.MID_GAME_FIELDS`.
        """
        if self._pending is None:
            raise RuntimeError("reveal() called before prepare_step()")
        return self._pending[2].revealed_view()

    def pending_declaration(self) -> tuple[str, list[int] | None]:
        """The sentence and any barrier our sealed step declares openly.

        One call, so a caller building a wire message never has to reach into
        the pending tuple. Both are already committed, and rule 15 obliges the
        barrier regardless.
        """
        if self._pending is None:
            raise RuntimeError("pending_declaration() called before prepare_step()")
        decision, hint, _record = self._pending
        barrier = ([int(decision.barrier[0]), int(decision.barrier[1])]
                   if decision.barrier else None)
        return hint, barrier

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

        **The first stated ending wins.** An unstated ending means survival --
        a peer that ran out the horizon has nothing to declare -- but only when
        it is the *first* thing they say. gal-roy1 drove us on 7 August at
        14:48 and sent two ``confirm_result`` calls in the same second: the
        first conceding ``CAPTURE`` at [5, 1], the second carrying no outcome
        at all. Under the old rule the second one read as survival and
        overwrote the concession, so our cop won the sub-game, was told it had
        won, and then quietly recorded the opponent as having survived.

        That is the worst available direction for this bug. Our own board still
        said ``capture`` (:meth:`TurnLoop.concede` keeps it), so the two halves
        of one peer disagreed, and rule 35 voids the match for *both* teams
        when the reports disagree -- costing gal-roy1 a game they did nothing
        wrong in. Nothing warned; the only trace was the word ``unstated`` in a
        log nobody reads during a game.

        The rule, the game it was written from and the casing it normalises all
        live in :mod:`p2pchase.runtime.opponent_ending`.
        """
        self.opponent_finished = record_ending(self.opponent_finished, outcome, self.sub_game)

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
        """Our pheromone intensity at the cells the opponent asked about.

        Read from the lagged broadcast field, never from ``my_scent`` (I-6).
        ``my_scent`` has already absorbed this turn's emission, so answering
        from it would peak on the cell we are standing on and hand over our
        position -- see :mod:`p2pchase.domain.scent_broadcast`.
        """
        transmitted = self.state.broadcast.transmitted(self.state.my_scent.grid)
        return {
            f"{int(c[0])},{int(c[1])}": transmitted.get((int(c[0]), int(c[1])), 0.0)
            for c in cells
        }

    def absorb_scent(self, samples: dict[str, float]) -> None:
        """Fold sampled opponent intensities into our posterior, then judge.

        Merged rather than replaced: over the network we sample only the cells
        we asked about, so a replace would throw away every earlier reading.

        Settling the standing verbal claim here keeps the networked path
        identical to the local harness -- the trail is what a claim is checked
        against, so this is the first moment the check is possible.

        :mod:`belief_probe` is called here rather than logged inline because it
        answers a question this method cannot: our cop has placed zero barriers
        across eight networked sub-games while placing six to eight per sub-game
        in the harness, and nothing we keep records what the posterior did.
        """
        self.state.sample_opponent_scent(samples, merge=True)
        self.state.belief.update_from_scent(self.state.opponent_scent)
        belief_probe.record(self.state, samples, judge_claim(self.state))

    # ------------------------------------------------------------ finishing
    def end_of_turn(self) -> None:
        self.state.end_of_full_turn()

    def final_reveal(self) -> list[dict[str, Any]]:
        """Our complete chain, nonces included. See :mod:`session_disclosure`."""
        return disclosure.final_reveal(self)

    def audit(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        """Verify their chain against the seals we hold. See :mod:`session_disclosure`."""
        return disclosure.audit(self, records)
