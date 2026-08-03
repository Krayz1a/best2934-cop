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

:func:`record_claim` and :func:`judge_claim` are the two halves of the last of
those: what the opponent said is written down when it arrives, and cross-examined
against the trail once the trail has been sampled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain.brains import BrainBase, Decision
from ..domain.crypto import commit
from ..domain.own_state import OwnState
from ..domain.protocol import StepIntent
from ..reports.artifacts import digest_payload
from ..strategy.hint_decoder import heading_from_hint
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


def record_claim(observer: OwnState, hint: str) -> str | None:
    """Note what the opponent's sentence asserted, without judging it yet.

    Judgement has to wait for the trail. At the moment a hint arrives we have
    not yet sampled the scent the opponent laid down on that same move, so
    there is physically nothing to check it against. Holding the claim until
    :func:`judge_claim` is not bookkeeping convenience -- it is the order in
    which the evidence actually becomes available.

    Returns the decoded heading, or ``None`` for a sentence naming no direction.
    An unparsable hint is uninformative, not dishonest, and scoring it would let
    an opponent silence our estimator simply by writing vaguer sentences.
    """
    observer.pending_claim = heading_from_hint(hint)
    return observer.pending_claim


def judge_claim(observer: OwnState) -> bool | None:
    """Cross-examine the standing claim against the trail, and act on the verdict.

    Takes the observer's ``OwnState`` rather than a :class:`Side` so the local
    harness and the networked session share one implementation -- the
    cross-examination has to be identical on both paths, or a strategy tuned
    against the harness would behave differently in a real match.

    Returns ``True`` if the claim matched the drift, ``False`` if it
    contradicted it, and ``None`` if there was nothing checkable. Only a claim
    that survived is allowed to move belief: a sentence we just caught
    contradicting the physical record earns a trust penalty and nothing else.
    """
    claim = observer.pending_claim
    observer.pending_claim = None
    honest = observer.belief.score_claim(claim, observer.trail_drift)
    if honest:
        observer.belief.update_from_hint(claim)
    return honest
