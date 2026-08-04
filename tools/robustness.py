"""Does the sweep's best setting hold up against opponents it was not tuned on?

A one-at-a-time sweep is run against a single fixed opponent, so its winner may
simply be exploiting that one opponent's habits. Adopting such a value would
look like tuning and behave like overfitting -- and in a league the opponent is
someone else's code entirely.

This script re-runs the most sensitive parameter against a panel of
structurally different thieves. A setting that wins on all of them is picking up
something about the *game*; one that wins on the tuned opponent alone is not.

Selection criterion is **max-min**, not max-mean: against an unknown opponent the
value worth having is the one with the best worst case.

    uv run python tools/robustness.py --seeds 40 --out results/robustness.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from p2pchase import constants  # noqa: E402
from p2pchase.runtime.local_match import run_local_match  # noqa: E402
from p2pchase.shared.config_schema import DEFAULT_SHARED, deep_merge  # noqa: E402

PARAMETER = "barrier_engage_range"
LEVELS = (1, 2, 3, 4, 5, 7)

#: A panel chosen for structural variety, not for weakness. Each optimises for
#: something different, so a cop setting that beats all of them is not exploiting
#: one opponent's blind spot.
THIEVES: dict[str, dict] = {
    "shipped": {},
    "area_obsessed": {"area_weight": 4.0, "distance_weight": 0.3},
    "distance_only": {"area_weight": 0.0, "distance_weight": 2.4},
    "always_endgame": {"endgame_window": 99, "adjacency_penalty": 12.0},
    "never_bluffs": {"bluff_period": 99, "adjacency_penalty": 3.0},
}


def capture_rate(shared: dict, cop_cfg: dict, thief_cfg: dict, seeds: int) -> float:
    captures = 0
    for seed in range(seeds):
        report, _cop, _thief = run_local_match(
            shared, seed=seed, strategy_cfg=cop_cfg, thief_strategy_cfg=thief_cfg,
            trash_talk_cfg={"provider": "template", "seed": seed},
        )
        captures += report.outcome == constants.OUTCOME_CAPTURE
    return captures / seeds


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=40)
    parser.add_argument("--out", default="results/robustness.json")
    args = parser.parse_args()

    shared = deep_merge({}, DEFAULT_SHARED)
    grid: dict[str, dict[str, float]] = {}

    header = f"{'thief':<16}" + "".join(f"{level:>8}" for level in LEVELS)
    print(header)
    for thief_name, thief_cfg in THIEVES.items():
        row = {str(level): capture_rate(shared, {PARAMETER: level}, thief_cfg, args.seeds)
               for level in LEVELS}
        grid[thief_name] = row
        print(f"{thief_name:<16}" + "".join(f"{row[str(x)]:>8.2f}" for x in LEVELS))

    summary = {
        str(level): {
            "mean": round(statistics.fmean(grid[t][str(level)] for t in THIEVES), 4),
            "worst_case": round(min(grid[t][str(level)] for t in THIEVES), 4),
        }
        for level in LEVELS
    }
    best = max(summary, key=lambda k: (summary[k]["worst_case"], summary[k]["mean"]))

    print(f"\n{'level':>8}{'mean':>10}{'worst case':>13}")
    for level in LEVELS:
        mark = "  <- best worst case" if str(level) == best else ""
        print(f"{level:>8}{summary[str(level)]['mean']:>10.3f}"
              f"{summary[str(level)]['worst_case']:>13.3f}{mark}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "_schema": "Cross-opponent robustness check for the most sensitive cop "
                   "parameter. Selection is by best worst case, because in a league "
                   "the opponent is unknown.",
        "parameter": PARAMETER,
        "seeds_per_cell": args.seeds,
        "thief_policies": THIEVES,
        "capture_rates": grid,
        "summary": summary,
        "selected": int(best),
    }, indent=2), encoding="utf-8")
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
