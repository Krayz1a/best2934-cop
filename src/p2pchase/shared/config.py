"""Configuration: the shared signed constitution and the private per-peer file.

Book Appendix B. Two formats, two very different jobs:

  * ``config/<role>/game.json`` -- SHARED. The agreed physics of the match.
    Both peers hold a BYTE-IDENTICAL copy (rule 11) and lock it with
    ``config_sha256``; the pre-game signature exchange refuses to play on any
    mismatch. JSON because it serialises canonically (sorted keys) and can
    therefore be hashed consistently across machines and languages.

  * ``config/<role>/game.toml`` -- PRIVATE. Port, opponent URL, strategy class,
    trash-talk provider, LLM settings, e-mail target, group identity. Never
    crosses the network, never signed, hand-edited, supports comments.

The decision test: "must the opponent agree to this value, or rely on it?" If
yes it belongs in the shared JSON; if no it stays in the private TOML.

Precedence is one-directional: where the shared JSON defines a key, it OVERLAYS
the private TOML, so a private file can never weaken a signed term.
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import constants as K
from ..domain.crypto import canonical_json, digest_payload


class ConfigError(RuntimeError):
    pass


# Keys whose defaults come from Appendix F. Used to fill gaps so the code always
# defaults to the book's example value when the parties agreed nothing else.
_DEFAULT_SHARED: dict[str, Any] = {
    "schema_version": K.SCHEMA_VERSION,
    "board_and_agents": {
        "grid_size": K.GRID_SIZE,
        "num_agents": K.NUM_AGENTS,
        "thief_start": list(K.THIEF_START),
        "cop_start": list(K.COP_START),
        "axis_origin_corner": K.AXIS_ORIGIN_CORNER,
        "axis_start_index": K.AXIS_START_INDEX,
    },
    "world": {"map_area": K.MAP_AREA, "hint_max_words": K.HINT_MAX_WORDS},
    "movement_and_barriers": {
        "move_set": list(K.MOVE_SET),
        "max_barriers": K.MAX_BARRIERS,
        "max_moves": K.MAX_MOVES,
        "survival_threshold": K.SURVIVAL_THRESHOLD,
    },
    "scoring": {
        "capture_cop": K.CAPTURE_COP,
        "capture_thief": K.CAPTURE_THIEF,
        "survival_cop": K.SURVIVAL_COP,
        "survival_thief": K.SURVIVAL_THIEF,
        "tie_score": K.TIE_SCORE,
        "technical_loss": K.TECHNICAL_LOSS,
    },
    "pheromones": {
        "pheromone_center_intensity": K.PHEROMONE_CENTER_INTENSITY,
        "pheromone_decay": K.PHEROMONE_DECAY,
        "pheromone_grid_size": K.PHEROMONE_GRID_SIZE,
        "pheromone_kernel": "book_table",
    },
    "network_and_league": {
        "response_timeout_sec": K.RESPONSE_TIMEOUT_SEC,
        "watchdog_timeout_sec": K.WATCHDOG_TIMEOUT_SEC,
        "num_games": 1,
        "diversity_reward": K.DIVERSITY_REWARD,
        "min_games_to_pass": K.MIN_GAMES_TO_PASS,
        "max_games_per_team": K.MAX_GAMES_PER_TEAM,
        "token_budget_per_series": K.TOKEN_BUDGET_PER_SERIES,
    },
    "rate_limiter_gatekeeper": {
        "requests_per_minute": K.REQUESTS_PER_MINUTE,
        "concurrent_requests": K.CONCURRENT_REQUESTS,
        "retry_backoff_sec": K.RETRY_BACKOFF_SEC,
        "max_retries": K.MAX_RETRIES,
        "queue_depth": K.QUEUE_DEPTH,
    },
}

# Parameters Appendix F marks PERMANENT. Changing any of these disqualifies the
# team, so the loader refuses to start rather than silently playing an illegal
# match (rule 12).
_PERMANENT: dict[str, Any] = {
    "board_and_agents.num_agents": K.NUM_AGENTS,
    "movement_and_barriers.move_set": list(K.MOVE_SET),
    "scoring.capture_cop": K.CAPTURE_COP,
    "scoring.capture_thief": K.CAPTURE_THIEF,
    "scoring.survival_cop": K.SURVIVAL_COP,
    "scoring.survival_thief": K.SURVIVAL_THIEF,
    "scoring.tie_score": K.TIE_SCORE,
    "pheromones.pheromone_center_intensity": K.PHEROMONE_CENTER_INTENSITY,
    "pheromones.pheromone_decay": K.PHEROMONE_DECAY,
    "pheromones.pheromone_grid_size": K.PHEROMONE_GRID_SIZE,
}

# Parameters Appendix F marks MINIMUM: negotiable upward only.
_MINIMUM: dict[str, int] = {
    "board_and_agents.grid_size": K.GRID_SIZE,
    "movement_and_barriers.max_barriers": K.MAX_BARRIERS,
    "movement_and_barriers.max_moves": K.MAX_MOVES,
    "movement_and_barriers.survival_threshold": K.SURVIVAL_THRESHOLD,
    "rate_limiter_gatekeeper.requests_per_minute": K.REQUESTS_PER_MINUTE,
    "rate_limiter_gatekeeper.concurrent_requests": K.CONCURRENT_REQUESTS,
    "rate_limiter_gatekeeper.retry_backoff_sec": K.RETRY_BACKOFF_SEC,
    "rate_limiter_gatekeeper.max_retries": K.MAX_RETRIES,
    "rate_limiter_gatekeeper.queue_depth": K.QUEUE_DEPTH,
}


def _dig(mapping: dict, dotted: str) -> Any:
    node: Any = mapping
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursive merge; ``overlay`` wins."""
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def validate_shared(shared: dict) -> list[str]:
    """Check the agreed config against Appendix F. Returns a list of problems."""
    problems: list[str] = []
    for dotted, expected in _PERMANENT.items():
        actual = _dig(shared, dotted)
        if actual is None:
            continue
        if isinstance(expected, float):
            same = abs(float(actual) - expected) < 1e-9
        elif isinstance(expected, list):
            same = list(actual) == expected
        else:
            same = actual == expected
        if not same:
            problems.append(
                f"PERMANENT parameter {dotted} is {actual!r}, must be {expected!r} "
                f"(Appendix F -- deviation disqualifies the team)"
            )
    for dotted, floor in _MINIMUM.items():
        actual = _dig(shared, dotted)
        if actual is None:
            continue
        if float(actual) < float(floor):
            problems.append(
                f"MINIMUM parameter {dotted} is {actual!r}, below the binding floor {floor!r} "
                f"(Appendix F -- may be raised by agreement, never lowered)"
            )
    return problems


@dataclass
class PeerConfig:
    """Everything one peer process needs to play."""

    role: str
    shared: dict[str, Any]
    private: dict[str, Any]
    shared_path: Path | None = None
    private_path: Path | None = None
    problems: list[str] = field(default_factory=list)

    # ------------------------------------------------------------- identity
    @property
    def group_id(self) -> str:
        return str(self.private.get("game", {}).get("group_id", "unknown-group"))

    @property
    def group_name(self) -> str:
        return str(self.private.get("game", {}).get("group_name", self.group_id))

    @property
    def members(self) -> list[str]:
        return list(self.private.get("game", {}).get("members", []))

    @property
    def repos(self) -> dict[str, str]:
        return dict(self.private.get("game", {}).get("repos", {}))

    # -------------------------------------------------------------- network
    @property
    def my_port(self) -> int:
        return int(self.private.get("network", {}).get("my_port", 8801))

    @property
    def opponent_url(self) -> str:
        return str(self.private.get("network", {}).get("opponent_url", ""))

    @property
    def public_url(self) -> str:
        """Tunnelled public URL, if one is configured (rule 10)."""
        return str(self.private.get("network", {}).get("public_url", ""))

    @property
    def turn_timeout(self) -> int:
        return int(
            self.private.get("network", {}).get(
                "turn_timeout_seconds",
                self.shared.get("network_and_league", {}).get("response_timeout_sec", 30),
            )
        )

    @property
    def watchdog_timeout(self) -> int:
        return int(self.shared.get("network_and_league", {}).get("watchdog_timeout_sec", 60))

    # ------------------------------------------------------------- strategy
    @property
    def strategy(self) -> dict[str, Any]:
        return dict(self.private.get("strategy", {}))

    @property
    def trash_talk(self) -> dict[str, Any]:
        return dict(self.private.get("trash_talk", {"provider": "template"}))

    @property
    def llm(self) -> dict[str, Any]:
        return dict(self.private.get("llm", {}))

    @property
    def email(self) -> dict[str, Any]:
        cfg = dict(self.private.get("email", {}))
        # The reporting address is fixed by Appendix F and is NOT negotiable.
        cfg["recipient"] = K.AGENT_REPORT_EMAIL
        return cfg

    # ---------------------------------------------------------------- hashes
    def config_sha256(self) -> str:
        """Digest of the agreed terms only -- the value both peers compare."""
        return digest_payload(self._agreed_terms())

    def _agreed_terms(self) -> dict[str, Any]:
        keys = (
            "schema_version",
            "board_and_agents",
            "world",
            "movement_and_barriers",
            "scoring",
            "pheromones",
            "network_and_league",
            "rate_limiter_gatekeeper",
        )
        return {k: self.shared[k] for k in keys if k in self.shared}

    def canonical_shared(self) -> str:
        return canonical_json(self._agreed_terms())


def load_config(config_dir: Path, role: str, strict: bool = True) -> PeerConfig:
    """Load ``game.toml`` (private) and overlay ``game.json`` (shared)."""
    config_dir = Path(config_dir)
    private_path = config_dir / "game.toml"
    shared_path = config_dir / "game.json"

    if not private_path.exists():
        raise ConfigError(f"missing private config: {private_path}")
    with private_path.open("rb") as handle:
        private = tomllib.load(handle)

    shared = dict(_DEFAULT_SHARED)
    if shared_path.exists():
        with shared_path.open("r", encoding="utf-8") as handle:
            agreed = json.load(handle)
        shared = _deep_merge(shared, agreed)

    problems = validate_shared(shared)
    if problems and strict:
        raise ConfigError(
            "the agreed configuration violates Appendix F:\n  - " + "\n  - ".join(problems)
        )

    return PeerConfig(
        role=role,
        shared=shared,
        private=private,
        shared_path=shared_path if shared_path.exists() else None,
        private_path=private_path,
        problems=problems,
    )
