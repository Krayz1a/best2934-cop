"""Frame sources for the live view.

Two generators, and the difference between them is what the picture is worth.

:func:`solo_frames` runs one agent with no opponent. Its belief only ever
diffuses, because nothing arrives to sharpen it -- useful for checking the
renderer, useless as a picture of the game.

:func:`match_frames` runs a genuine two-sided sub-game and yields the chosen
peer's view of it. The posterior now tightens when a scent sample lands and
smears again as the trail decays, which is the behaviour worth screenshotting
and the behaviour the README is actually asking to see.

Both yield ``local_view()`` dicts. Neither can leak the objective board, because
neither ever holds it: the two sides are separate ``Side`` objects with separate
boards, exactly as in the match harness (rules 8, 9).
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from typing import Any

from .. import constants
from ..domain.board import build_board
from ..domain.brains import load_brain
from ..domain.own_state import build_own_state
from ..runtime.local_match import build_side, exchange_scent, play_half_turn
from ..strategy.landmarks import heading_word, pick_landmark
from ..strategy.talk_engine import build_talk_engine
from ..strategy.talk_prompt import TalkRequest

Frame = tuple[dict[str, Any], str]


def solo_frames(config: dict[str, Any], role: str, strategy: dict, trash_talk: dict,
                llm: dict, seed: int = 0) -> Iterator[Frame]:
    """One agent moving alone. Belief diffuses and never sharpens."""
    rng = random.Random(seed)
    state = build_own_state(config, role, build_board(config))
    brain = load_brain(role, strategy, config)
    talk = build_talk_engine(trash_talk, llm)
    max_moves = int(config["movement_and_barriers"]["max_moves"])
    map_area = config.get("world", {}).get("map_area", "")
    max_words = int(config.get("world", {}).get("hint_max_words", 15))

    yield state.local_view(), ""
    for step in range(1, max_moves + 1):
        decision = brain.decide(state)
        hint = talk.compose(TalkRequest(
            role=role, step=step, intent=decision.intent,
            heading=heading_word(decision.move),
            landmark=pick_landmark(map_area, rng), max_words=max_words,
            steps_remaining=state.survival_threshold - state.step,
        ))
        state.apply_own_move(decision.move, decision.barrier)
        state.end_of_full_turn()
        state.belief.predict()
        yield state.local_view(), hint


def match_frames(config: dict[str, Any], watch_role: str, strategy: dict,
                 trash_talk: dict, llm: dict, seed: int = 0,
                 group: str = "us", opponent: str = "them") -> Iterator[Frame]:
    """A real two-sided sub-game, seen from ``watch_role``'s side only."""
    rng = random.Random(seed)
    cop = build_side(config, constants.ROLE_COP, group, strategy, trash_talk, llm)
    thief = build_side(config, constants.ROLE_THIEF, opponent, strategy, trash_talk, llm)
    watched = cop if watch_role == constants.ROLE_COP else thief

    map_area = config.get("world", {}).get("map_area", constants.MAP_AREA)
    max_words = int(config.get("world", {}).get("hint_max_words", constants.HINT_MAX_WORDS))
    max_moves = int(config["movement_and_barriers"]["max_moves"])

    yield watched.state.local_view(), ""
    for step in range(1, max_moves + 1):
        hint = ""
        for side, other in ((cop, thief), (thief, cop)):
            spoken = play_half_turn(side, other, step, 1, map_area, max_words, rng)
            if side is not watched:
                # What the watched peer hears is the OPPONENT's actual claim --
                # possibly a lie, which is the point of showing it.
                hint = spoken

        exchange_scent(cop, thief)
        if cop.state.position == thief.state.position or thief.state.thief_is_boxed_in():
            watched.state.finished = True
            watched.state.outcome = constants.OUTCOME_CAPTURE
            yield watched.state.local_view(), hint
            return

        cop.state.end_of_full_turn()
        thief.state.end_of_full_turn()
        yield watched.state.local_view(), hint

        if thief.state.survival_reached():
            watched.state.finished = True
            watched.state.outcome = constants.OUTCOME_SURVIVAL
            return
