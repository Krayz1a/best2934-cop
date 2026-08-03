"""Local two-agent match harness (book ch10, PRD stage 1).

This runs both agents in ONE process. That is legal only as a development
harness -- it is explicitly not how a league match is played. Rule 1 requires
the cop and the thief to run in two fully separate processes, rule 2 forbids
shared memory between them, and rule 10 puts a real match across the public
internet through a tunnel.

The separation discipline survives anyway: each side gets its own ``Board`` and
its own ``OwnState``, and neither is ever handed the other's position.
Everything one side learns arrives through the channels the network would carry
-- the declared barrier, the revealed move, the sampled scent and the verbal
hint. That is what makes this a faithful rehearsal rather than a shortcut, and
it is why the logs it produces are real logs.

Its job is to generate those logs, the artifacts and the screenshots the README
requires, without needing a second machine or an opponent.
"""

from __future__ import annotations

import random
from typing import Any

from .. import constants as K
from ..domain.board import build_board
from ..domain.brains import load_brain
from ..domain.crypto import audit_records
from ..domain.own_state import build_own_state
from ..domain.scoring import ScoreTable, build_score_table
from ..domain.smell import build_kernel, kernel_fingerprint
from ..strategy.talk_engine import build_talk_engine
from ..strategy.talk_prompt import TalkRequest
from ..strategy.landmarks import heading_word, pick_landmark
from .match_side import MatchReport, Side, cells_matching_heading


def build_side(config: dict[str, Any], role: str, group_id: str,
                strategy_cfg: dict, trash_talk_cfg: dict, llm_cfg: dict) -> Side:
    """Assemble one peer with its own board, state, brain and talk engine."""
    return Side(
        group_id=group_id,
        state=build_own_state(config, role, build_board(config)),
        brain=load_brain(role, strategy_cfg, config),
        talk=build_talk_engine(trash_talk_cfg, llm_cfg),
    )


def play_half_turn(side: Side, opponent: Side, step: int, sub_game: int,
                   map_area: str, max_words: int, rng: random.Random) -> str:
    """One agent acts; the opponent learns only what the wire would carry.

    Returns the hint that went out, so a caller rendering the match can show
    what the opponent actually said rather than inventing a second sentence.
    """
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
    side.note_intent(decision)
    side.seal_step(step, decision, hint, sub_game)
    side.state.apply_own_move(decision.move, decision.barrier)

    # A barrier is declared openly and truthfully (rules 15, 16), so the
    # opponent learns its exact cell. A move is NOT a position: the opponent
    # learns only which way we went.
    opponent.state.apply_opponent_move(
        decision.move, list(decision.barrier) if decision.barrier else None
    )

    # The claim is cross-examined against the trail, and the trust weight this
    # peer assigns to future hints moves accordingly.
    claimed = cells_matching_heading(opponent.state, decision.move)
    honest = opponent.state.belief.score_hint(claimed, opponent.state.opponent_scent)
    opponent.state.belief.update_from_hint(claimed if honest else set())
    return hint


def exchange_scent(cop: Side, thief: Side) -> None:
    """Each side samples only its OPPONENT's field, then folds it into belief."""
    cop.state.sample_opponent_scent(thief.state.my_scent.as_dict())
    thief.state.sample_opponent_scent(cop.state.my_scent.as_dict())
    for side in (cop, thief):
        side.state.belief.update_from_scent(side.state.opponent_scent)


def terminal_outcome(cop: Side, thief: Side) -> str | None:
    """Check the two ways a sub-game ends early, in the book's order."""
    if cop.state.position == thief.state.position:
        return K.OUTCOME_CAPTURE
    if thief.state.thief_is_boxed_in():
        return K.OUTCOME_CAPTURE
    return None


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

    cop = build_side(config, K.ROLE_COP, cop_group, strategy_cfg, trash_talk_cfg, llm_cfg)
    thief = build_side(config, K.ROLE_THIEF, thief_group, strategy_cfg, trash_talk_cfg, llm_cfg)

    outcome: str | None = None
    max_moves = int(config["movement_and_barriers"]["max_moves"])

    for step in range(1, max_moves + 1):
        for side, opponent in ((cop, thief), (thief, cop)):
            play_half_turn(side, opponent, step, sub_game, map_area, max_words, rng)

        exchange_scent(cop, thief)
        outcome = terminal_outcome(cop, thief)
        if outcome is not None:
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

    report = MatchReport(
        outcome=outcome,
        steps=cop.state.step,
        winner_role=table.winner_role(outcome),
        score=table.award(outcome),
        cop_audit=audit_records(cop.records).as_dict(),
        thief_audit=audit_records(thief.records).as_dict(),
        scent_fingerprint=kernel_fingerprint(
            build_kernel(config), float(config["pheromones"]["pheromone_decay"])
        ),
        tokens={cop.group_id: cop.talk.tokens_used, thief.group_id: thief.talk.tokens_used},
    )
    return report, cop, thief
