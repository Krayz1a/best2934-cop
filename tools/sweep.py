"""One-at-a-time parameter sweep over the strategy weights.

OAT (one-at-a-time) rather than a full factorial: with nine tunables and five
levels each, a factorial would be ~2M matches, and the interactions it would buy
are not what we need. The question here is which weights the outcome is
*sensitive* to at all, so each parameter is varied alone with the rest at their
defaults, and every cell is averaged over many seeds.

Each measurement plays a full sub-game against the shipped opponent. The
opponent is held fixed, so a change in the capture rate is attributable to the
parameter under test rather than to both sides drifting at once.

    uv run python tools/sweep.py --seeds 40 --out results/sweep.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from p2pchase import constants  # noqa: E402
from p2pchase.runtime.local_match import run_local_match  # noqa: E402
from p2pchase.shared.config_schema import DEFAULT_SHARED, deep_merge  # noqa: E402

#: (role, parameter, levels). Every list **includes the shipped default** and
#: brackets it on both sides. Including it matters: a sweep that skips its own
#: default cannot say whether the default sits on a plateau or on a cliff edge,
#: which is the main thing a sweep is for.
SWEEP: tuple[tuple[str, str, tuple[float, ...]], ...] = (
    ("police", "mobility_weight", (0.0, 0.01, 0.25, 0.5, 1.0, 2.0)),
    ("police", "idle_penalty", (0.0, 0.35, 1.0, 2.0)),
    ("police", "barrier_engage_range", (1, 2, 3, 4, 5, 7)),
    ("police", "barrier_min_gain", (0, 1, 2, 4)),
    ("thief", "area_weight", (0.0, 0.5, 1.0, 2.0, 4.0)),
    ("thief", "distance_weight", (0.0, 0.6, 1.2, 2.4)),
    ("thief", "adjacency_penalty", (0.0, 3.0, 6.0, 12.0)),
    ("thief", "endgame_window", (0, 2, 4, 8)),
    ("thief", "bluff_period", (1, 2, 4, 99)),
)


def one_match(shared: dict, cop_cfg: dict, thief_cfg: dict, seed: int) -> dict[str, Any]:
    """Play one sub-game and pull out the numbers worth comparing."""
    report, cop, thief = run_local_match(
        shared, sub_game=1, seed=seed,
        strategy_cfg=cop_cfg, thief_strategy_cfg=thief_cfg,
        trash_talk_cfg={"provider": "template", "seed": seed},
    )
    belief = cop.state.belief
    return {
        "captured": report.outcome == constants.OUTCOME_CAPTURE,
        "steps": report.steps,
        "cop_entropy": belief.entropy(),
        "cop_trust": belief.trust,
        "hints_seen": belief.hints_seen,
        "hints_contradicted": belief.hints_contradicted,
        "lies_told": thief.lies_told,
        "tokens": sum(report.tokens.values()),
        "both_logs_verify": report.both_logs_verify,
    }


def aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean of every numeric column, plus the capture rate and its spread."""
    n = len(runs)
    capture_rate = sum(r["captured"] for r in runs) / n
    return {
        "matches": n,
        "capture_rate": round(capture_rate, 4),
        # Binomial standard error -- the honest error bar for a rate over n trials.
        "capture_stderr": round((capture_rate * (1 - capture_rate) / n) ** 0.5, 4),
        "mean_steps": round(statistics.fmean(r["steps"] for r in runs), 2),
        "mean_cop_entropy": round(statistics.fmean(r["cop_entropy"] for r in runs), 4),
        "mean_cop_trust": round(statistics.fmean(r["cop_trust"] for r in runs), 4),
        "mean_lies_told": round(statistics.fmean(r["lies_told"] for r in runs), 2),
        "contradiction_rate": round(
            sum(r["hints_contradicted"] for r in runs) / max(1, sum(r["hints_seen"] for r in runs)),
            4,
        ),
        "tokens": sum(r["tokens"] for r in runs),
        "all_logs_verified": all(r["both_logs_verify"] for r in runs),
    }


def sweep_one(shared: dict, role: str, name: str, levels, seeds: int) -> list[dict[str, Any]]:
    """Vary one parameter across its levels, everything else at its default."""
    rows = []
    for level in levels:
        cfg = {name: level}
        cop_cfg = cfg if role == constants.ROLE_COP else {}
        thief_cfg = cfg if role == constants.ROLE_THIEF else {}
        runs = [one_match(shared, cop_cfg, thief_cfg, seed) for seed in range(seeds)]
        rows.append({"role": role, "parameter": name, "value": level, **aggregate(runs)})
        print(f"  {name:<22} = {level!s:<6} capture={rows[-1]['capture_rate']:.3f} "
              f"steps={rows[-1]['mean_steps']:.1f}", flush=True)
    return rows


def baseline(shared: dict, seeds: int) -> dict[str, Any]:
    """The shipped defaults, measured the same way as every swept level."""
    runs = [one_match(shared, {}, {}, seed) for seed in range(seeds)]
    return {"role": "both", "parameter": "baseline", "value": "default", **aggregate(runs)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=40,
                        help="matches per level; more seeds, tighter error bars")
    parser.add_argument("--out", default="results/sweep.json")
    args = parser.parse_args()

    shared = deep_merge({}, DEFAULT_SHARED)
    started = time.time()

    print(f"baseline over {args.seeds} seeds...", flush=True)
    rows = [baseline(shared, args.seeds)]
    print(f"  capture={rows[0]['capture_rate']:.3f} steps={rows[0]['mean_steps']:.1f}\n")

    for role, name, levels in SWEEP:
        print(f"{role}: {name}", flush=True)
        rows.extend(sweep_one(shared, role, name, levels, args.seeds))

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "_schema": "One-at-a-time strategy parameter sweep. Each row is one "
                   "parameter level averaged over N independent sub-games.",
        "seeds_per_level": args.seeds,
        "elapsed_seconds": round(time.time() - started, 1),
        "rows": rows,
    }, indent=2), encoding="utf-8")
    print(f"\n{len(rows)} rows -> {out} ({time.time() - started:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
