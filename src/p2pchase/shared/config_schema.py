"""The Appendix F contract: defaults, immutable terms and the validator.

Book Appendix F splits every quantitative parameter into three classes, and the
distinction is what this module encodes:

``PERMANENT``
    May not change at all. Deviating disqualifies the team (rule 12), so the
    loader refuses to start rather than quietly play an illegal match.

``MINIMUM``
    A binding floor. Two teams may agree to raise it -- a larger board, more
    barriers, a longer match -- but never to lower it.

Everything else is freely negotiable, and the values here are the defaults the
book requires the code to fall back to "in the absence of an explicit agreement
between the parties".

Keeping the contract in its own module means the validator can be unit-tested
without loading a file, and the table can be read as a specification rather
than dug out of loader plumbing.
"""

from __future__ import annotations

from typing import Any

from .. import constants
from .version import CONFIG_VERSION

DEFAULT_SHARED: dict[str, Any] = {
    "version": CONFIG_VERSION,
    "schema_version": constants.SCHEMA_VERSION,
    "board_and_agents": {
        "grid_size": constants.GRID_SIZE,
        "num_agents": constants.NUM_AGENTS,
        "thief_start": list(constants.THIEF_START),
        "cop_start": list(constants.COP_START),
        "axis_origin_corner": constants.AXIS_ORIGIN_CORNER,
        "axis_start_index": constants.AXIS_START_INDEX,
    },
    "world": {"map_area": constants.MAP_AREA, "hint_max_words": constants.HINT_MAX_WORDS},
    "movement_and_barriers": {
        "move_set": list(constants.MOVE_SET),
        "max_barriers": constants.MAX_BARRIERS,
        "max_moves": constants.MAX_MOVES,
        "survival_threshold": constants.SURVIVAL_THRESHOLD,
    },
    "scoring": {
        "capture_cop": constants.CAPTURE_COP,
        "capture_thief": constants.CAPTURE_THIEF,
        "survival_cop": constants.SURVIVAL_COP,
        "survival_thief": constants.SURVIVAL_THIEF,
        "tie_score": constants.TIE_SCORE,
        "technical_loss": constants.TECHNICAL_LOSS,
    },
    "pheromones": {
        "pheromone_center_intensity": constants.PHEROMONE_CENTER_INTENSITY,
        "pheromone_decay": constants.PHEROMONE_DECAY,
        "pheromone_grid_size": constants.PHEROMONE_GRID_SIZE,
        "pheromone_kernel": "book_table",
    },
    "network_and_league": {
        "response_timeout_sec": constants.RESPONSE_TIMEOUT_SEC,
        "watchdog_timeout_sec": constants.WATCHDOG_TIMEOUT_SEC,
        "num_sub_games": constants.NUM_SUB_GAMES,
        "diversity_reward": constants.DIVERSITY_REWARD,
        "min_games_to_pass": constants.MIN_GAMES_TO_PASS,
        "max_games_per_team": constants.MAX_GAMES_PER_TEAM,
        "token_budget_per_series": constants.TOKEN_BUDGET_PER_SERIES,
    },
}

PERMANENT: dict[str, Any] = {
    "board_and_agents.num_agents": constants.NUM_AGENTS,
    "movement_and_barriers.move_set": list(constants.MOVE_SET),
    "scoring.capture_cop": constants.CAPTURE_COP,
    "scoring.capture_thief": constants.CAPTURE_THIEF,
    "scoring.survival_cop": constants.SURVIVAL_COP,
    "scoring.survival_thief": constants.SURVIVAL_THIEF,
    "scoring.tie_score": constants.TIE_SCORE,
    "pheromones.pheromone_center_intensity": constants.PHEROMONE_CENTER_INTENSITY,
    "pheromones.pheromone_decay": constants.PHEROMONE_DECAY,
    "pheromones.pheromone_grid_size": constants.PHEROMONE_GRID_SIZE,
}

MINIMUM: dict[str, int] = {
    "board_and_agents.grid_size": constants.GRID_SIZE,
    "movement_and_barriers.max_barriers": constants.MAX_BARRIERS,
    "movement_and_barriers.max_moves": constants.MAX_MOVES,
    "movement_and_barriers.survival_threshold": constants.SURVIVAL_THRESHOLD,
}

#: Section names covered by ``config_sha256``. Naming metadata is excluded
#: because it is derived and therefore identical on both sides by construction.
AGREED_SECTIONS: tuple[str, ...] = (
    "schema_version",
    "board_and_agents",
    "world",
    "movement_and_barriers",
    "scoring",
    "pheromones",
    "network_and_league",
)


def dig(mapping: dict[str, Any], dotted: str) -> Any:
    """Fetch a dotted path, returning ``None`` for any missing link."""
    node: Any = mapping
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursive merge in which ``overlay`` wins at every leaf."""
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _matches(actual: Any, expected: Any) -> bool:
    """Compare against a permanent term, tolerating float representation."""
    if isinstance(expected, float):
        return abs(float(actual) - expected) < 1e-9
    if isinstance(expected, list):
        return list(actual) == expected
    return bool(actual == expected)


def validate_shared(shared: dict[str, Any]) -> list[str]:
    """Check an agreed config against Appendix F; return every problem found.

    All problems are collected rather than raised one at a time, so a team
    negotiating a config sees the complete list in a single round trip instead
    of discovering violations one message at a time.
    """
    problems: list[str] = []
    for dotted, expected in PERMANENT.items():
        actual = dig(shared, dotted)
        if actual is not None and not _matches(actual, expected):
            problems.append(
                f"PERMANENT parameter {dotted} is {actual!r}, must be {expected!r} "
                f"(Appendix F -- deviation disqualifies the team)"
            )
    for dotted, floor in MINIMUM.items():
        actual = dig(shared, dotted)
        if actual is not None and float(actual) < float(floor):
            problems.append(
                f"MINIMUM parameter {dotted} is {actual!r}, below the binding floor "
                f"{floor!r} (Appendix F -- may be raised by agreement, never lowered)"
            )
    return problems
