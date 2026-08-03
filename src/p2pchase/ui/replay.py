"""Replay viewer and integrity enforcement (book ch7.4-7.5).

Rule 20 makes this a gate, not a nicety: a match log is only trustworthy if it
can be replayed and verified step by step, and a screenshot of this tool showing
``Verified OK`` is a mandatory component of the README (ch9.4.2, item 5).

Verification recomputes, for every recorded step, ``SHA-256`` over the canonical
payload plus the disclosed nonce, and compares it against the commitment that
was announced *before* the move was revealed. A single altered bit anywhere in
the payload changes the digest completely, so tampering cannot hide. There is no
statistical judgement here and no room for interpretation -- the cryptography
decides, not a person (rule 19: a mismatch is a technical loss, score 0).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..domain.board import Board, BoardGeometry, Coord
from ..domain.crypto import verify


@dataclass
class StepVerdict:
    """The verification outcome for a single recorded step."""

    index: int
    step: int
    role: str
    move: str
    hint: str
    barrier: list[int] | None
    ok: bool
    reason: str = ""

    @property
    def badge(self) -> str:
        return "OK" if self.ok else "TAMPERED"


@dataclass
class ReplayResult:
    """Whole-log verdict."""

    game_id: str
    sub_game: int
    role: str
    outcome: str
    verdicts: list[StepVerdict] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(v.ok for v in self.verdicts)

    @property
    def verified_steps(self) -> int:
        return sum(1 for v in self.verdicts if v.ok)

    @property
    def failed_steps(self) -> list[int]:
        return [v.step for v in self.verdicts if not v.ok]

    def banner(self) -> str:
        if self.passed:
            return f"Verified OK — {self.verified_steps}/{len(self.verdicts)} steps"
        return (
            f"INTEGRITY FAILURE — tampering proven at step(s) "
            f"{', '.join(str(s) for s in self.failed_steps)} "
            f"(technical loss, score 0)"
        )


def load_log(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def verify_log(log: dict[str, Any]) -> ReplayResult:
    """Recompute every commitment in a disclosed log."""
    summary = log.get("summary", {})
    result = ReplayResult(
        game_id=str(log.get("game_id", "unknown")),
        sub_game=int(summary.get("sub_game_number", 0)),
        role=str(summary.get("role", "unknown")),
        outcome=str(summary.get("result", "unknown")),
    )

    for index, record in enumerate(log.get("records", [])):
        payload = record.get("payload")
        nonce = record.get("nonce")
        announced = record.get("commit")

        if not isinstance(payload, dict):
            result.verdicts.append(
                StepVerdict(index, index, "?", "?", "", None, False, "record has no payload")
            )
            continue

        step = int(payload.get("step", index))
        role = str(payload.get("role", payload.get("type", "system")))
        move = str(payload.get("move", "-"))
        hint = str(payload.get("hint", ""))
        barrier = payload.get("barrier")

        if not isinstance(nonce, str) or not isinstance(announced, str):
            result.verdicts.append(
                StepVerdict(index, step, role, move, hint, barrier, False,
                            "nonce or commitment missing from the disclosed log")
            )
            continue

        ok = verify(payload, nonce, announced)
        result.verdicts.append(
            StepVerdict(index, step, role, move, hint, barrier, ok,
                        "" if ok else "recomputed digest does not match the announced commitment")
        )

    return result


def reconstruct_boards(log: dict[str, Any], grid_size: int = 7) -> Iterator[tuple[StepVerdict, Board, Coord | None]]:
    """Replay the board forward, yielding the state after each verified step.

    Only the log owner's own movement can be reconstructed -- that is the whole
    point of the epistemology: the log records what this peer did and what its
    opponent declared, never a global god's-eye view.
    """
    geometry = BoardGeometry(grid_size)
    board = Board(geometry=geometry)
    position: Coord | None = None

    for verdict in verify_log(log).verdicts:
        if verdict.barrier:
            board.barriers.add((int(verdict.barrier[0]), int(verdict.barrier[1])))
        elif position is not None and verdict.move in ("N", "S", "E", "W"):
            target = board.target_of(position, verdict.move)
            if board.is_passable(target):
                position = target
        yield verdict, board, position


def render_text(result: ReplayResult, limit: int | None = None) -> str:
    """Plain-text replay report — what the screenshot in the README captures."""
    lines = [
        f"Replay — game {result.game_id}  sub-game {result.sub_game:02d}  role {result.role}",
        f"Outcome recorded: {result.outcome}",
        "",
        f"{'step':>4}  {'role':<8} {'move':<5} {'barrier':<9} {'status':<9} hint",
        "-" * 78,
    ]
    shown = result.verdicts if limit is None else result.verdicts[:limit]
    for v in shown:
        barrier = f"{tuple(v.barrier)}" if v.barrier else "-"
        hint = (v.hint[:34] + "…") if len(v.hint) > 35 else v.hint
        lines.append(
            f"{v.step:>4}  {v.role:<8} {v.move:<5} {barrier:<9} {v.badge:<9} {hint}"
        )
    if limit is not None and len(result.verdicts) > limit:
        lines.append(f"... {len(result.verdicts) - limit} more steps")
    lines += ["-" * 78, result.banner()]
    return "\n".join(lines)


def replay_file(path: str | Path, limit: int | None = None) -> ReplayResult:
    """Verify a log file and print the report. Returns the result for tests."""
    result = verify_log(load_log(path))
    print(render_text(result, limit=limit))
    return result
