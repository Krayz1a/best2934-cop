"""Configuration loading: the signed constitution and the private setup file.

Book Appendix B draws a line this loader enforces. Two files, two very
different jobs:

``config/<role>/game.json`` -- SHARED
    The agreed physics of the match. Both peers hold a BYTE-IDENTICAL copy
    (rule 11) and lock it with ``config_sha256``; the pre-game exchange refuses
    to play on any mismatch. JSON because it serialises canonically and can
    therefore be hashed identically across machines and languages.

``config/<role>/setup.json`` -- PRIVATE
    Port, opponent URL, strategy class, trash-talk provider, LLM settings,
    group identity. Never crosses the network, never signed.

The decision test is one question: *must the opponent agree to this value, or
rely on it?* If yes it is shared; if no it stays private.

Precedence is one-directional. Where the shared file defines a key it overlays
the defaults, and the private file cannot touch it -- so a local edit can never
weaken a signed term.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import constants
from .config_schema import DEFAULT_SHARED, deep_merge, validate_shared
from .paths import config_dir as default_config_dir
from .peer_config import PeerConfig
from .rate_limits import DEFAULT_RATE_LIMITS, load_rate_limits
from .version import CONFIG_VERSION, validate_config_version

__all__ = ["ConfigError", "PeerConfig", "load_config", "load_json", "validate_shared"]


class ConfigError(RuntimeError):
    """Raised when configuration is missing, malformed or illegal."""


def load_json(path: Path) -> dict[str, Any]:
    """Read a JSON config, turning parse errors into a config-level failure."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object, found {type(data).__name__}")
    return data


def _load_shared(path: Path, strict: bool) -> tuple[dict[str, Any], list[str]]:
    """Merge the agreed file over the Appendix F defaults and validate it."""
    shared: dict[str, Any] = deep_merge({}, DEFAULT_SHARED)
    if path.exists():
        agreed = load_json(path)
        validate_config_version(agreed.get("version"), CONFIG_VERSION, str(path))
        shared = deep_merge(shared, agreed)

    problems = validate_shared(shared)
    if problems and strict:
        raise ConfigError(
            "the agreed configuration violates Appendix F:\n  - " + "\n  - ".join(problems)
        )
    return shared, problems


def load_config(
    config_dir: Path | str | None = None,
    role: str = constants.DEFAULT_ROLE,
    strict: bool = True,
) -> PeerConfig:
    """Assemble a :class:`PeerConfig` for one peer process.

    ``strict`` exists for the negotiation flow: a peer must be able to *inspect*
    an opponent's proposed config and report what is wrong with it, which means
    loading a file it would refuse to play on.
    """
    base = Path(config_dir) if config_dir is not None else default_config_dir() / role
    setup_path = base / "setup.json"
    shared_path = base / "game.json"

    if not setup_path.exists():
        raise ConfigError(
            f"missing private setup file: {setup_path}. "
            f"Copy config/{role}/setup.example.json and fill in your own values."
        )
    setup = load_json(setup_path)
    validate_config_version(setup.get("version"), CONFIG_VERSION, str(setup_path))

    shared, problems = _load_shared(shared_path, strict)

    limits_path = base.parent / "rate_limits.json"
    rate_limits = load_rate_limits(limits_path) if limits_path.exists() else DEFAULT_RATE_LIMITS

    return PeerConfig(
        role=role,
        shared=shared,
        setup=setup,
        rate_limits=rate_limits,
        shared_path=shared_path if shared_path.exists() else None,
        setup_path=setup_path,
        problems=problems,
    )
