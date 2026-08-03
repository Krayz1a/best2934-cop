"""One peer's private world during a match, and how it perceives the other.

The separation this module enforces is the point of the whole project. A
``Side`` owns its own board, its own state and its own commit log. It is never
handed the opponent's position, because in a real match nobody has it.

Everything one side learns about the other arrives through exactly four
channels, and they carry very different amounts of truth:

* a **declared barrier** -- open and truthful (rules 15, 16), so the cell is known
* a **revealed move** -- a direction, not a position
* a **sampled scent** -- unforgeable, but noisy and decaying
* a **verbal hint** -- possibly a lie, worth exactly as much as our trust in it

:func:`cells_matching_heading` is where the second of those is turned into
something a belief map can use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain.brains import BrainBase, Decision
from ..domain.crypto import commit
from ..domain.own_state import OwnState
from ..domain.protocol import StepIntent
from ..reports.artifacts import digest_payload
from ..strategy.talk_engine import TalkEngine


@dataclass
class Side:
    """One peer's complete, private world.

    Input:  its own ``OwnState``, brain and talk engine.
    Output: a growing list of commit/reveal ``records`` -- the match log.
    Setup:  ``group_id`` identifies the team in every artifact it writes.
    """

    group_id: str
    state: OwnState
    brain: BrainBase
    talk: TalkEngine
    records: list[dict[str, Any]] = field(default_factory=list)
    honest_hints: int = 0
    lies_told: int = 0

    @property
    def role(self) -> str:
        return self.state.role

    def seal_step(self, step: int, decision: Decision, hint: str, sub_game: int) -> None:
        """Commit this step exactly as the network protocol would.

        The commitment is computed over the sealed payload *before* anything is
        revealed, which is what makes the later disclosure checkable rather than
        merely plausible.
        """
        intent = StepIntent(
            step=step,
            role=self.role,
            sub_game_number=sub_game,
            move=decision.move,
            hint=hint,
            intent=decision.intent,
            barrier=list(decision.barrier) if decision.barrier else None,
            state_digest=digest_payload(self.state.state_digest_source()),
        )
        self.records.append(commit(intent.payload()).audit_view())

    def note_intent(self, decision: Decision) -> None:
        """Track our own honesty, for the strategy report."""
        if decision.intent == "lie":
            self.lies_told += 1
        else:
            self.honest_hints += 1


@dataclass
class MatchReport:
    """The outcome of one sub-game, from both peers' independent records."""

    outcome: str
    steps: int
    winner_role: str | None
    score: dict[str, int]
    cop_audit: dict[str, Any]
    thief_audit: dict[str, Any]
    scent_fingerprint: str
    tokens: dict[str, int]

    @property
    def both_logs_verify(self) -> bool:
        """True only when neither side's commit chain shows tampering."""
        return bool(self.cop_audit.get("passed") and self.thief_audit.get("passed"))

    def as_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "steps": self.steps,
            "winner_role": self.winner_role,
            "score": dict(self.score),
            "cop_audit": dict(self.cop_audit),
            "thief_audit": dict(self.thief_audit),
            "scent_fingerprint": self.scent_fingerprint,
            "tokens": dict(self.tokens),
            "both_logs_verify": self.both_logs_verify,
        }


def cells_matching_heading(observer: OwnState, move: str) -> set:
    """Decode a movement claim into the cells it would be consistent with.

    We do not know where the opponent stands, so a claim of "north" cannot be
    read as a position. It is read instead as a claim about the *shape* of our
    belief cloud: the cells reachable by moving north from somewhere we
    currently think the opponent might be. STAY tells us nothing about
    direction, so it claims nothing.
    """
    if move not in ("N", "S", "E", "W"):
        return set()
    board = observer.board
    claimed = set()
    for cell, probability in observer.belief.grid.items():
        if probability <= 0:
            continue
        target = board.target_of(cell, move)
        if board.is_passable(target):
            claimed.add(target)
    return claimed
