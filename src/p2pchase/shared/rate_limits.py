"""The rate-limit contract, versioned separately from the game (guidelines §5.2).

Rate limits live apart from ``game.json`` on purpose. The game config describes
physics two teams negotiate with each other; these numbers describe how hard we
are willing to lean on Google's mail quota, which is between us and Google. They
change for different reasons and therefore carry their own version.

Appendix F Table 19 marks every value here as a MINIMUM: a team may throttle
itself harder than the book requires, never softer. ``validate_rate_limits``
enforces that floor in the same collect-everything style as the game validator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .. import constants
from .version import RATE_LIMITS_VERSION, validate_config_version

#: Fallback used when ``config/rate_limits.json`` is absent. Mirrors Table 19.
DEFAULT_RATE_LIMITS: dict[str, Any] = {
    "version": RATE_LIMITS_VERSION,
    "services": {
        "default": {
            "requests_per_minute": constants.REQUESTS_PER_MINUTE,
            "concurrent_max": constants.CONCURRENT_REQUESTS,
            "retry_after_seconds": constants.RETRY_BACKOFF_SEC,
            "max_retries": constants.MAX_RETRIES,
            "queue_depth": constants.QUEUE_DEPTH,
            "daily_limit": 200,
            "burst_threshold": 12,
            "burst_window_seconds": 60,
        }
    },
}

#: Ceilings, not floors: a *lower* configured value is stricter and therefore
#: always allowed. Only these two are floors -- see the sign of the comparison.
_FLOORS: dict[str, int] = {
    "requests_per_minute": constants.REQUESTS_PER_MINUTE,
    "concurrent_max": constants.CONCURRENT_REQUESTS,
    "retry_after_seconds": constants.RETRY_BACKOFF_SEC,
    "max_retries": constants.MAX_RETRIES,
    "queue_depth": constants.QUEUE_DEPTH,
}


class RateLimitError(RuntimeError):
    """Raised when the rate-limit file is unusable or below the binding floor."""


def service_limits(config: dict[str, Any], service: str = "default") -> dict[str, Any]:
    """Settings for one service, falling back to ``default`` then to the book."""
    services = config.get("services", {})
    merged = dict(DEFAULT_RATE_LIMITS["services"]["default"])
    merged.update(services.get("default", {}))
    if service != "default":
        merged.update(services.get(service, {}))
    return merged


def validate_rate_limits(config: dict[str, Any]) -> list[str]:
    """Return every Table 19 floor the configuration falls below."""
    problems: list[str] = []
    for name, limits in config.get("services", {}).items():
        for key, floor in _FLOORS.items():
            value = limits.get(key)
            if value is not None and float(value) < float(floor):
                problems.append(
                    f"services.{name}.{key} is {value!r}, below the binding floor "
                    f"{floor!r} (Appendix F Table 19 -- may be raised, never lowered)"
                )
    return problems


def load_rate_limits(path: Path, strict: bool = True) -> dict[str, Any]:
    """Load and validate ``rate_limits.json``."""
    import json

    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            config = json.load(handle)
    except json.JSONDecodeError as exc:
        raise RateLimitError(f"{path} is not valid JSON: {exc}") from exc

    validate_config_version(config.get("version"), RATE_LIMITS_VERSION, str(path))
    problems = validate_rate_limits(config)
    if problems and strict:
        raise RateLimitError(
            "rate limits fall below Appendix F Table 19:\n  - " + "\n  - ".join(problems)
        )
    return config
