"""Shared setup for the figure scripts: paths, saving, and a match to plot."""

from __future__ import annotations

import random
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: a grader's machine may have no display
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from p2pchase import constants  # noqa: E402
from p2pchase.runtime.local_match import (  # noqa: E402
    build_side,
    exchange_scent,
    play_half_turn,
)
from p2pchase.shared.config_schema import DEFAULT_SHARED, deep_merge  # noqa: E402

ASSETS = ROOT / "assets"
RESULTS = ROOT / "results"
GRID = 7


def save(fig, name: str) -> None:
    """Write one figure into ``assets/`` and report the path."""
    ASSETS.mkdir(parents=True, exist_ok=True)
    path = ASSETS / name
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  {path.relative_to(ROOT)}")


def play(steps: int = 22, seed: int = 7):
    """One real two-sided sub-game, with the cop's entropy recorded per turn.

    Returns both sides so a figure can draw the true thief cell as a reference
    mark. The cop itself never receives it -- the plot has an information
    advantage the agent does not.
    """
    shared = deep_merge({}, DEFAULT_SHARED)
    rng = random.Random(seed)
    talk = {"provider": "template", "seed": seed}
    cop = build_side(shared, constants.ROLE_COP, "cop", {}, talk, {})
    thief = build_side(shared, constants.ROLE_THIEF, "rival", {}, talk, {})

    entropy = []
    for step in range(1, steps + 1):
        for side, other in ((cop, thief), (thief, cop)):
            play_half_turn(side, other, step, 1, "New York", 15, rng)
        exchange_scent(cop, thief)
        entropy.append(cop.state.belief.entropy())
        if cop.state.position == thief.state.position:
            break
        cop.state.end_of_full_turn()
        thief.state.end_of_full_turn()
    return cop, thief, entropy
