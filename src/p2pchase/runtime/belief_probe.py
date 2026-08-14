"""One log line per round, aimed at the question our artifacts cannot answer.

Written to diagnose a cop that placed **zero** barriers against imreeyal across
three networked sub-games while placing 5.2 per sub-game against gal-roy1 and
six to eight in the local harness -- and captured nothing in either match.

It answered on its first run, and not the way the question was posed. The
posterior is **fine**: the peak tracks the real thief cell for cell -- (3,3),
(4,3), (5,3), (6,3) against a thief actually walking that path -- with 25 to 30
scent cells arriving per round. What it also showed is that the peak sits at
distance 5 and stays there, because two agents that both move one cell per turn
cannot close, and the fielded ``barrier_engage_range`` was 1.

So the gate was the defect and the belief never was. See
``config/police/setup.json`` for the re-derivation to 4 and for the correction of
the miscount that framed this module's original question -- the sealed record
encodes a barrier *inside* the move string as ``BARRIER:r,c``, and counting a
separate key found none anywhere.

Kept, and worth keeping. The four artifacts carry positions, commitments and
outcomes and no posterior at all, so "a field arrives and fails to inform us"
and "almost nothing arrives" are indistinguishable after the fact without it.
Two numbers separate them: how many cells arrived, and how flat we are
afterwards.

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
