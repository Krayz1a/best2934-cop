"""Render every report figure from the experiment data in ``results/``.

Kept as a script rather than living only in the notebook so the figures can be
regenerated in one command, and so the notebook stays about analysis rather
than plotting boilerplate. Everything is written to ``assets/``.

    uv sync --extra analysis
    uv run python tools/sweep.py --seeds 60
    uv run python tools/trust_experiment.py --seeds 30
    uv run python tools/make_figures.py

Figures 4 and 5 read recorded data and are skipped, with a message, when their
input file is absent -- so a fresh checkout still produces the model figures.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fig_experiments import figure_sweep, figure_trust  # noqa: E402
from fig_model import figure_belief_and_scent, figure_entropy, figure_kernel  # noqa: E402


def main() -> int:
    print("rendering figures into assets/ ...")
    figure_kernel()
    figure_belief_and_scent()
    figure_entropy()
    figure_trust()
    figure_sweep()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
