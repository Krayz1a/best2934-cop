"""Keep what the opponent actually sent, so the next diagnosis uses bytes.

Written after a diagnosis we could not finish. On 2026-08-09 we played imreeyal
six sub-games, lost all six, and audited 0 of 36 steps in every one -- and then
could not say why, because their disclosed chain lives in
``PeerSession.opponent_records`` and nothing ever writes it anywhere. We had
their verdict and not their evidence.

Worse, our cop played a **byte-identical 34-move path in all three sub-games it
played**: same opening cell, same route, same finish, against a live opponent.
A cop reacting to a scent trail cannot do that. Either their ``smell_grid``
arrives empty or we drop it -- and the parse chain tests clean end to end, so
the answer is very likely the former. "Very likely" is exactly the kind of
claim this module exists to replace: three separate root causes were published
to two opponents today on reasoning that ran ahead of the data, and all three
were withdrawn.

Off unless ``P2PCHASE_CAPTURE_DIR`` names a directory. This is a diagnostic,
not a feature: it writes nothing during a normal match, and what it writes is
the opponent's own message as it arrived -- never a reconstruction, because a
reconstruction is the thing under suspicion.

**It never writes into the repository.** The capture holds another team's raw
wire traffic, and both of ours are public.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

CAPTURE_DIR_ENV = "P2PCHASE_CAPTURE_DIR"


def capture_dir() -> Path | None:
    """The directory to write to, or ``None`` when capture is off."""
    raw = os.environ.get(CAPTURE_DIR_ENV, "").strip()
    return Path(raw) if raw else None


def note_turn(step: int, message: dict[str, Any]) -> None:
    """Log the shape of one received turn, and keep the message itself.

    The log line is the half that costs nothing and answers the current
    question: a ``smell_grid`` of size 0 arriving every step is the whole
    explanation for a cop that never deviates.
    """
    grid = message.get("smell_grid")
    size = len(grid) if isinstance(grid, dict) else -1
    LOGGER.info("their turn step %s: smell_grid entries=%d, hint=%r, keys=%s",
                step, size, str(message.get("hint", ""))[:40],
                ",".join(sorted(message)) or "(none)")
    _append("turns", {"step": step, "message": message})


def note_audit(payload: dict[str, Any]) -> None:
    """Keep their whole disclosed chain, which is what an audit failure needs."""
    records = payload.get("records")
    LOGGER.info("their audit: sender=%r records=%d result_claim=%r",
                payload.get("sender"),
                len(records) if isinstance(records, list) else -1,
                payload.get("result_claim"))
    _append("audits", {"payload": payload})


def _append(name: str, entry: dict[str, Any]) -> None:
    """One JSON object per line. Append-only so a crash keeps what came before.

    Failures are logged and swallowed: a diagnostic that can abort a live
    sub-game is worse than no diagnostic at all, and rule 6 charges both teams
    for the stall.
    """
    directory = capture_dir()
    if directory is None:
        return
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with (directory / f"{name}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    except (OSError, TypeError, ValueError) as error:
        LOGGER.error("could not capture %s: %s", name, error)
