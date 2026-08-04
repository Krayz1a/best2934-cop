"""Figures built from the recorded experiment data in ``results/``."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
from fig_common import RESULTS, save

LABELS = {
    "always_lies": "thief lies every turn",
    "never_lies": "thief never lies",
    "rationed": "shipped thief (rationed deception)",
}


def figure_trust() -> None:
    """Trust dynamics under three honesty policies."""
    path = RESULTS / "trust.json"
    if not path.exists():
        print("  (skipped fig4: run tools/trust_experiment.py first)")
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    data = payload["policies"]

    fig, ax = plt.subplots(figsize=(7.5, 4))
    for key, style in (("never_lies", "o-"), ("rationed", "s-"), ("always_lies", "^-")):
        curve = data[key]["mean_trust_curve"]
        ax.plot(range(1, len(curve) + 1), curve, style, markersize=4,
                label=f"{LABELS[key]} (final {data[key]['final_trust_mean']:.3f})")
    ax.axhline(0.5, color="grey", linestyle=":", label="neutral prior")
    ax.axhline(0.02, color="darkred", linestyle=":", label="trust floor")
    ax.set_xlabel("turn")
    ax.set_ylabel("cop's trust in the thief's claims")
    ax.set_title(f"Lying costs the liar its channel  (mean of {payload['seeds']} seeds)")
    ax.set_ylim(0, 1.32)
    ax.legend(fontsize=8, loc="upper left", ncols=2, framealpha=0.9)
    ax.grid(alpha=0.3)

    # The honest curves genuinely dip mid-game. Annotated so a reader cannot
    # mistake it for a shrinking sample: every honest run survives all 30 turns,
    # so the mean is over the same runs at every point.
    alive = data["never_lies"].get("runs_alive_curve")
    if alive and min(alive) == max(alive):
        ax.text(0.98, 0.02, f"honest runs alive at every turn: {alive[0]}/{alive[0]}",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=7, color="grey")
    save(fig, "fig4_trust.png")


def figure_sweep() -> None:
    """Which weights the outcome is actually sensitive to."""
    path = RESULTS / "sweep.json"
    if not path.exists():
        print("  (skipped fig5: run tools/sweep.py first)")
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["rows"]
    base = next(r for r in rows if r["parameter"] == "baseline")
    params = [p for p in dict.fromkeys(r["parameter"] for r in rows) if p != "baseline"]

    cols = 3
    n_rows = (len(params) + cols - 1) // cols
    fig, axes = plt.subplots(n_rows, cols, figsize=(4 * cols, 3 * n_rows))
    for ax, name in zip(axes.flat, params, strict=False):
        pts = [r for r in rows if r["parameter"] == name]
        x = list(range(len(pts)))
        ax.errorbar(x, [p["capture_rate"] for p in pts],
                    yerr=[p["capture_stderr"] for p in pts], fmt="o-", capsize=3)
        ax.axhline(base["capture_rate"], color="grey", linestyle=":",
                   label=f"all-defaults baseline {base['capture_rate']:.2f}")
        ax.set_xticks(x)
        ax.set_xticklabels([str(p["value"]) for p in pts], fontsize=7)
        ax.set_title(f"{pts[0]['role']}: {name}", fontsize=9)
        ax.set_ylabel("capture rate", fontsize=8)
        ax.set_ylim(-0.05, 1.05)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=6)
    for ax in axes.flat[len(params):]:
        ax.axis("off")
    fig.suptitle(f"One-at-a-time sensitivity, {data['seeds_per_level']} matches per level "
                 "(error bars: binomial standard error)", fontsize=11)
    fig.tight_layout()
    save(fig, "fig5_sweep.png")
