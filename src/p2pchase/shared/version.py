"""Explicit version tracking (guidelines §8.1, Table 2).

Three things carry a version in this project and they are deliberately
independent, because they change for different reasons:

``CODE_VERSION``
    The agent implementation. Bumped on any behavioural change. It is signed
    into the Step-0 declaration so an opponent can prove which build played.

``CONFIG_VERSION``
    The schema of ``config/*.json``. Bumped when a key is added, renamed or
    given new semantics -- never when a *value* changes, since values are
    negotiated per match.

``RATE_LIMITS_VERSION``
    The gatekeeper's rate-limit contract, versioned separately because it is
    tuned against Google's quota rather than against the game.

Startup calls :func:`validate_config_version`, so a config written for an
older schema is refused loudly instead of being half-understood.
"""

from __future__ import annotations

from typing import Final

CODE_VERSION: Final[str] = "1.00"
CONFIG_VERSION: Final[str] = "1.00"
RATE_LIMITS_VERSION: Final[str] = "1.00"

__all__ = [
    "CODE_VERSION",
    "CONFIG_VERSION",
    "RATE_LIMITS_VERSION",
    "VersionMismatchError",
    "is_compatible",
    "validate_config_version",
]


class VersionMismatchError(RuntimeError):
    """Raised when a configuration file was written for an incompatible schema."""


def _major(version: str) -> int:
    """Leading component of a ``MAJOR.MINOR`` version string."""
    head = version.split(".", 1)[0].strip()
    if not head.isdigit():
        raise VersionMismatchError(f"malformed version string: {version!r}")
    return int(head)


def is_compatible(found: str, expected: str) -> bool:
    """Same major version means the reader understands every key it needs.

    A minor bump only ever adds optional keys, so an older minor is readable.
    A major bump means a key changed meaning, which is never safe to guess at.
    """
    return _major(found) == _major(expected)


def validate_config_version(found: str | None, expected: str = CONFIG_VERSION,
                            what: str = "configuration") -> None:
    """Refuse to start on an incompatible config rather than misread it."""
    if found is None:
        raise VersionMismatchError(
            f"{what} has no 'version' key; expected {expected}. "
            "Every versioned artifact must declare its schema version."
        )
    if not is_compatible(found, expected):
        raise VersionMismatchError(
            f"{what} declares version {found}, but this build understands "
            f"{expected}. Refusing to run on a config it may misinterpret."
        )
