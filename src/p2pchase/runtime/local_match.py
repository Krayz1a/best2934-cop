"""Local two-agent match harness (book ch10, PRD stage 1).

This runs both agents in ONE process. That is legal only as a development
harness -- it is explicitly not how a league match is played. Rule 1 requires
the cop and the thief to run in two fully separate processes, and rule 2
forbids any shared memory between them; a league match additionally runs across
the public internet through a tunnel (rule 10).

The separation discipline is preserved even here: each side gets its own
``Board`` and its own ``OwnState``, and neither is ever handed the other's
position. Everything one side learns about the other arrives through the same
channels the network would carry -- the declared barrier, the revealed move, the
sampled scent field and the verbal hint. That is what makes the harness a
faithful rehearsal rather than a shortcut.

Its job is to generate real logs, real artifacts and the screenshots the README
requires, without needing a second machine or an opponent.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import constants as K
from ..domain.board import build_board
from ..domain.brains import BrainBase, load_brain
from ..domain.crypto import commit, audit_records
from ..domain.own_state import OwnState, build_own_state
from ..domain.protocol import StepIntent
from ..domain.scoring import ScoreTable, build_score_table
from ..domain.smell import build_kernel, kernel_fingerprint
from ..reports import artifacts as A
from ..strategy.talk_providers import (
    TalkEngine, TalkRequest, build_talk_engine, heading_word, pick_landmark,
)


@dataclass
class Side:
    """One peer's complete, private world."""

    group_id: str
    state: OwnState
    brain: BrainBase
    talk: TalkEngine
    records: list[dict[str, Any]] = field(default_factory=list)
    honest_hints: int = 0
    lies_told: int = 0

    @property
    def role(self) -> str:
        return self.state.role


@dataclass
class MatchReport:
    outcome: str
    steps: int
    winner_role: str | None
    score: dict[str, int]
    cop_audit: dict[str, Any]
    thief_audit: dict[str, Any]
    scent_fingerprint: str
    tokens: dict[str, int]


def _seal_step(side: Side, step: int, decision, hint: str, sub_game: int) -> None:
    """Commit the step, exactly as the network protocol would."""
    intent = StepIntent(
        step=step,
        role=side.role,
        sub_game_number=sub_game,
        move=decision.move,
        hint=hint,
        intent=decision.intent,
        barrier=list(decision.barrier) if decision.barrier else None,
        state_digest=A.digest_payload(side.state.state_digest_source()),
    )
    side.records.append(commit(intent.payload()).audit_view())


def run_local_match(
    config: dict[str, Any],
    cop_group: str = "best2934-cop",
    thief_group: str = "best2934-thief",
    sub_game: int = 1,
    seed: int = 0,
    strategy_cfg: dict | None = None,
    trash_talk_cfg: dict | None = None,
    llm_cfg: dict | None = None,
) -> tuple[MatchReport, Side, Side]:
    """Play one complete sub-game locally and return both peers' logs."""
    rng = random.Random(seed)
    strategy_cfg = strategy_cfg or {}
    trash_talk_cfg = trash_talk_cfg or {"provider": "template", "seed": seed}
    llm_cfg = llm_cfg or {}

    table: ScoreTable = build_score_table(config)
    map_area = config.get("world", {}).get("map_area", K.MAP_AREA)
    max_words = int(config.get("world", {}).get("hint_max_words", K.HINT_MAX_WORDS))

    cop = Side(
        group_id=cop_group,
        state=build_own_state(config, K.ROLE_COP, build_board(config)),
        brain=load_brain(K.ROLE_COP, strategy_cfg, config),
        talk=build_talk_engine(trash_talk_cfg, llm_cfg),
    )
    thief = Side(
        group_id=thief_group,
        state=build_own_state(config, K.ROLE_THIEF, build_board(config)),
        brain=load_brain(K.ROLE_THIEF, strategy_cfg, config),
        talk=build_talk_engine(trash_talk_cfg, llm_cfg),
    )

    outcome: str | None = None
    max_moves = int(config["movement_and_barriers"]["max_moves"])

    for step in range(1, max_moves + 1):
        for side, opponent in ((cop, thief), (thief, cop)):
            decision = side.brain.decide(side.state)
            hint = side.talk.compose(
                TalkRequest(
                    role=side.role,
                    step=step,
                    intent=decision.intent,
                    heading=heading_word(decision.move),
                    landmark=pick_landmark(map_area, rng),
                    max_words=max_words,
                    steps_remaining=side.state.survival_threshold - side.state.step,
                )
            )
            if decision.intent == K.INTENT_LIE:
                side.lies_told += 1
            else:
                side.honest_hints += 1

            _seal_step(side, step, decision, hint, sub_game)
            side.state.apply_own_move(decision.move, decision.barrier)

            # A barrier is declared openly and truthfully (rules 15, 16), so the
            # opponent learns its exact cell. A move is NOT a position: the
            # opponent only learns which way we went.
            opponent.state.apply_opponent_move(
                decision.move, list(decision.barrier) if decision.barrier else None
            )

            # The hint is cross-examined against the trail, and the trust weight
            # this peer assigns to future hints moves accordingly.
            claimed = _cells_matching_heading(opponent.state, decision.move)
            honest = opponent.state.belief.score_hint(claimed, opponent.state.opponent_scent)
            opponent.state.belief.update_from_hint(claimed if honest else set())

        # Each side samples only its OPPONENT's field.
        cop.state.sample_opponent_scent(thief.state.my_scent.as_dict())
        thief.state.sample_opponent_scent(cop.state.my_scent.as_dict())
        for side in (cop, thief):
            side.state.belief.update_from_scent(side.state.opponent_scent)

        if cop.state.position == thief.state.position:
            outcome = K.OUTCOME_CAPTURE
            break
        if thief.state.thief_is_boxed_in():
            outcome = K.OUTCOME_CAPTURE
            break

        cop.state.end_of_full_turn()
        thief.state.end_of_full_turn()

        if thief.state.survival_reached():
            outcome = K.OUTCOME_SURVIVAL
            break

    if outcome is None:
        # Move ceiling reached without a capture: the thief endured.
        outcome = K.OUTCOME_SURVIVAL

    for side in (cop, thief):
        side.state.finished = True
        side.state.outcome = outcome

    kernel = build_kernel(config)
    decay = float(config["pheromones"]["pheromone_decay"])

    report = MatchReport(
        outcome=outcome,
        steps=cop.state.step,
        winner_role=table.winner_role(outcome),
        score=table.award(outcome),
        cop_audit=audit_records(cop.records).as_dict(),
        thief_audit=audit_records(thief.records).as_dict(),
        scent_fingerprint=kernel_fingerprint(kernel, decay),
        tokens={cop.group_id: cop.talk.tokens_used, thief.group_id: thief.talk.tokens_used},
    )
    return report, cop, thief


def _cells_matching_heading(observer: OwnState, move: str) -> set:
    """Decode a movement claim into the cells it would be consistent with.

    We do not know where the opponent stands, so a claim of "north" is read as
    a claim about the *shape* of its belief cloud: the cells reachable by moving
    north from somewhere we currently think it might be.
    """
    if move not in ("N", "S", "E", "W"):
        return set()
    board = observer.board
    claimed = set()
    for cell, probability in observer.belief.grid.items():
        if probability <= 0:
            continue
        target = board.target_of(cell, move)
        if board.is_passable(target):
            claimed.add(target)
    return claimed
