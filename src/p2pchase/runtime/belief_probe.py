"""One log line per round, aimed at the question our artifacts cannot answer.

Our cop places six to eight barriers per sub-game in the local harness. It has
placed **zero** across eight networked sub-games against two different
opponents -- roughly 280 steps without a single one, and no captures either.

The fielded ``barrier_engage_range`` is 1: the cop considers a wall only when
the belief peak is within one step. In the harness it sits that close on 56% of
turns, which is why the sweep chose the value and why it has never once fired in
a real match. The gate is not the defect. The posterior underneath it is.

In the harness both peers hand over their whole transmitted field. Over the wire
we get whatever the opponent decided to push, in whatever shape, and nothing we
keep records what our belief did with it -- the four artifacts carry positions,
commitments and outcomes, and no posterior at all. So the difference between "a
field arrives and fails to inform us" and "almost nothing arrives" is currently
undiagnosable after the fact, which is why eight sub-games have gone by without
it being diagnosed.

Two numbers separate the cases: how many cells arrived, and how flat we are
afterwards. Both go here, per round, so the next real match answers it.

This writes to the log, never to an artifact. The log artifact's ``summary``
field list is the course template's, and matching it exactly is worth more than
carrying our own diagnostics inside it.
"""

from __future__ import annotations

import logging
from typing import Any

LOGGER = logging.getLogger(__name__)

CREDIBILITY = {True: "credible", False: "doubtful"}


def record(state: Any, samples: dict[str, float], honest: bool | None) -> None:
    """Log what arrived this round and what our posterior made of it."""
    peak = state.belief.most_likely()
    LOGGER.info(
        "step %s: %d scent cells in; entropy %.3f, peak %s at distance %s; "
        "claim %s, trust %.3f",
        state.step, len(samples), state.belief.entropy(), peak,
        state.board.manhattan(state.position, peak) if peak else "n/a",
        CREDIBILITY.get(honest, "unreadable"), state.belief.trust,
    )
