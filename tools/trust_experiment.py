"""Trust dynamics against three honesty policies.

The claim this project makes about its verbal channel is that lying is
detectable and that detection has consequences. That claim is worth a
measurement rather than an assertion, so this script runs the same match three
times with only the thief's honesty policy changed -- same board, same seed,
same movement weights -- and records the cop's trust coefficient after every
turn.

    uv run python tools/trust_experiment.py --seeds 30 --out results/trust.json
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from p2pchase import constants  # noqa: E402
from p2pchase.domain.thief_brain import ThiefBrain  # noqa: E402
from p2pchase.runtime.local_match import (  # noqa: E402
    build_side,
    exchange_scent,
    play_half_turn,
)
from p2pchase.shared.config_schema import DEFAULT_SHARED, deep_merge  # noqa: E402


class AlwaysLies(ThiefBrain):
    """Every hint is false. The worst possible use of the channel."""

    def _choose_intent(self, state) -> str:
        return constants.INTENT_LIE


class NeverLies(ThiefBrain):
    """The control group: identical movement, no false claim ever."""

    def _choose_intent(self, state) -> str:
        return constants.INTENT_TRUTH


POLICIES = {"always_lies": AlwaysLies, "never_lies": NeverLies, "rationed": ThiefBrain}


def trust_trace(shared: dict, brain_cls, seed: int, steps: int = 30) -> dict[str, Any]:
    """One match; the cop's trust in the thief recorded after every turn."""
    rng = random.Random(seed)
    talk = {"provider": "template", "seed": seed}
    cop = build_side(shared, constants.ROLE_COP, "cop", {}, talk, {})
    thief = build_side(shared, constants.ROLE_THIEF, "rival", {}, talk, {})
    thief.brain = brain_cls()

    trust, entropy = [], []
    for step in range(1, steps + 1):
        for side, other in ((cop, thief), (thief, cop)):
            play_half_turn(side, other, step, 1, "New York", 15, rng)
        exchange_scent(cop, thief)
        trust.append(round(cop.state.belief.trust, 4))
        entropy.append(round(cop.state.belief.entropy(), 4))
        if cop.state.position == thief.state.position:
            break
        cop.state.end_of_full_turn()
        thief.state.end_of_full_turn()

    belief = cop.state.belief
    return {
        "trust": trust,
        "entropy": entropy,
        "final_trust": belief.trust,
        "hints_seen": belief.hints_seen,
        "hints_contradicted": belief.hints_contradicted,
        "lies_told": thief.lies_told,
        "captured": cop.state.position == thief.state.position,
    }


def _mean_curve(traces: list[list[float]]) -> list[float]:
    """Average the curves turn by turn, over however many runs got that far."""
    longest = max(len(t) for t in traces)
    return [
        round(statistics.fmean(t[i] for t in traces if len(t) > i), 4)
        for i in range(longest)
    ]


def _alive_curve(traces: list[list[float]]) -> list[int]:
    """How many runs were still going at each turn.

    Published alongside the mean because a curve averaged over a shrinking set
    of runs can bend for reasons that have nothing to do with the quantity being
    plotted. A reader can only rule that out if the count is visible.
    """
    longest = max(len(t) for t in traces)
    return [sum(len(t) > i for t in traces) for i in range(longest)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=30)
    parser.add_argument("--out", default="results/trust.json")
    args = parser.parse_args()

    shared = deep_merge({}, DEFAULT_SHARED)
    summary: dict[str, Any] = {}

    for name, brain_cls in POLICIES.items():
        runs = [trust_trace(shared, brain_cls, seed) for seed in range(args.seeds)]
        seen = sum(r["hints_seen"] for r in runs)
        summary[name] = {
            "runs": len(runs),
            "mean_trust_curve": _mean_curve([r["trust"] for r in runs]),
            "mean_entropy_curve": _mean_curve([r["entropy"] for r in runs]),
            "runs_alive_curve": _alive_curve([r["trust"] for r in runs]),
            "final_trust_mean": round(statistics.fmean(r["final_trust"] for r in runs), 4),
            "final_trust_stdev": round(statistics.stdev(r["final_trust"] for r in runs), 4)
            if len(runs) > 1 else 0.0,
            "claims_seen": seen,
            "claims_contradicted": sum(r["hints_contradicted"] for r in runs),
            "contradiction_rate": round(
                sum(r["hints_contradicted"] for r in runs) / max(1, seen), 4),
            "mean_lies_told": round(statistics.fmean(r["lies_told"] for r in runs), 2),
            "capture_rate": round(sum(r["captured"] for r in runs) / len(runs), 4),
        }
        row = summary[name]
        print(f"{name:<12} final trust {row['final_trust_mean']:.3f} "
              f"± {row['final_trust_stdev']:.3f}   "
              f"contradicted {row['contradiction_rate']:.1%}   "
              f"lies {row['mean_lies_told']:.1f}")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "_schema": "Trust dynamics under three thief honesty policies. Movement "
                   "weights, board and seeds are identical across policies; only "
                   "the truthfulness of the sentences differs.",
        "seeds": args.seeds,
        "policies": summary,
    }, indent=2), encoding="utf-8")
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
