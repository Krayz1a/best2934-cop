"""Project-relative path resolution (guidelines §14.3 -- never absolute paths).

Hard-coding ``/home/someone/best2934-cop`` works exactly once, on one machine.
Every path in this project is therefore derived at run time from one of three
sources, in descending priority:

1. ``P2PCHASE_ROOT`` -- an explicit override, used when the package is
   installed as a wheel and the source tree is somewhere else entirely.
2. The location of this file, walked up to the repository root. Correct for a
   checkout or an editable install, which is how a match is actually played.
3. The current working directory, as a last resort.

The layout constants below are the directory contract from guidelines §2.4.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_ROOT = "P2PCHASE_ROOT"


def project_root() -> Path:
    """Repository root, resolved without ever hard-coding a machine path."""
    override = os.environ.get(_ENV_ROOT)
    if override:
        return Path(override).expanduser().resolve()

    here = Path(__file__).resolve()
    # src/p2pchase/shared/paths.py -> shared -> p2pchase -> src -> root
    candidate = here.parents[3]
    if (candidate / "pyproject.toml").exists():
        return candidate
    return Path.cwd().resolve()


def config_dir() -> Path:
    return project_root() / "config"


def role_config_dir(role: str) -> Path:
    """Per-role config, so cop and thief can be launched from one checkout."""
    return config_dir() / role


def artifacts_dir() -> Path:
    return project_root() / "artifacts"


def logs_dir() -> Path:
    return project_root() / "logs"


def results_dir() -> Path:
    return project_root() / "results"


def assets_dir() -> Path:
    return project_root() / "assets"


def ensure(path: Path) -> Path:
    """Create a directory if absent and return it, so callers can chain."""
    path.mkdir(parents=True, exist_ok=True)
    return path
