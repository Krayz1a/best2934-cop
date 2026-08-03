"""Wire protocol: message envelopes, step records and the turn state machine.

Book chapters 2, 5 and 8. Every message crossing the network is one of a small,
closed set of types, and the legal orderings are enforced by an explicit state
machine (rules 4, 5). An out-of-order or unexpected message is rejected rather
than tolerated -- a permissive protocol is how distributed systems deadlock.

Turn structure for one step, with both peers symmetric:

    COMMIT -> ACK -> REVEAL -> APPLY

and once per match, at the end:

    FINAL_REVEAL -> AUDIT -> AGREE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .. import constants


class MessageType(StrEnum):
    HELLO = "hello"
    NEGOTIATE = "negotiate"
    STEP0 = "step0_declaration"
    COMMIT = "commit"
    ACK = "ack"
    REVEAL = "reveal"
    CAPTURE_CLAIM = "capture_claim"
    CAPTURE_RESPONSE = "capture_response"
    FINAL_REVEAL = "final_reveal"
    AUDIT_RESULT = "audit_result"
    AGREE_RESULT = "agree_result"
    ABORT = "abort"


class Phase(StrEnum):
    """Where a single step currently stands."""

    IDLE = "idle"
    NEGOTIATING = "negotiating"
    DECLARED = "declared"
    AWAIT_COMMIT = "await_commit"
    AWAIT_ACK = "await_ack"
    AWAIT_REVEAL = "await_reveal"
    APPLIED = "applied"
    FINALISING = "finalising"
    AUDITED = "audited"
    DONE = "done"
    ABORTED = "aborted"


# Legal transitions. Anything not listed is rejected (rule 5).
_TRANSITIONS: dict[Phase, set[Phase]] = {
    Phase.IDLE: {Phase.NEGOTIATING, Phase.ABORTED},
    Phase.NEGOTIATING: {Phase.DECLARED, Phase.ABORTED},
    Phase.DECLARED: {Phase.AWAIT_COMMIT, Phase.ABORTED},
    Phase.AWAIT_COMMIT: {Phase.AWAIT_ACK, Phase.ABORTED},
    Phase.AWAIT_ACK: {Phase.AWAIT_REVEAL, Phase.ABORTED},
    Phase.AWAIT_REVEAL: {Phase.APPLIED, Phase.ABORTED},
    Phase.APPLIED: {Phase.AWAIT_COMMIT, Phase.FINALISING, Phase.ABORTED},
    Phase.FINALISING: {Phase.AUDITED, Phase.ABORTED},
    Phase.AUDITED: {Phase.DONE, Phase.ABORTED},
    Phase.DONE: set(),
    Phase.ABORTED: set(),
}


class IllegalTransitionError(RuntimeError):
    """Raised when the protocol is driven into an undefined state."""


@dataclass
class StateMachine:
    """Explicit, auditable game state machine (book ch8.3).

    Deadlock in a two-party protocol with no referee is not a nuisance, it is a
    technical loss for both sides. Making the legal graph explicit means an
    impossible message is caught at the boundary instead of corrupting state.
    """

    phase: Phase = Phase.IDLE
    history: list[tuple[Phase, Phase]] = field(default_factory=list)

    def can(self, target: Phase) -> bool:
        return target in _TRANSITIONS.get(self.phase, set())

    def to(self, target: Phase) -> Phase:
        if not self.can(target):
            raise IllegalTransitionError(f"illegal transition {self.phase.value} -> {target.value}")
        self.history.append((self.phase, target))
        self.phase = target
        return self.phase

    def abort(self, reason: str = "") -> None:
        self.history.append((self.phase, Phase.ABORTED))
        self.phase = Phase.ABORTED
        self.abort_reason = reason  # type: ignore[attr-defined]


@dataclass
class Envelope:
    """A message on the wire."""

    type: MessageType
    game_id: str
    sub_game_number: int
    step: int
    sender_group: str
    sender_role: str
    body: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "game_id": self.game_id,
            "sub_game_number": self.sub_game_number,
            "step": self.step,
            "sender_group": self.sender_group,
            "sender_role": self.sender_role,
            "body": self.body,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Envelope:
        return cls(
            type=MessageType(data["type"]),
            game_id=str(data.get("game_id", "")),
            sub_game_number=int(data.get("sub_game_number", 1)),
            step=int(data.get("step", 0)),
            sender_group=str(data.get("sender_group", "")),
            sender_role=str(data.get("sender_role", "")),
            body=dict(data.get("body", {})),
        )


@dataclass
class StepIntent:
    """What this peer decided to do on one step, before it is sealed.

    ``intent`` is the truth/lie flag. It is committed BEFORE the hint is
    revealed, which is what stops an agent from claiming after the fact that it
    "meant" to lie (book ch5.3.1).
    """

    step: int
    role: str
    sub_game_number: int
    move: str
    hint: str
    intent: str = constants.INTENT_TRUTH
    barrier: list[int] | None = None
    state_digest: str = ""

    def payload(self) -> dict[str, Any]:
        """The object that gets sealed into the SHA-256 commitment."""
        body: dict[str, Any] = {
            "step": self.step,
            "role": self.role,
            "sub_game": self.sub_game_number,
            "state": self.state_digest,
            "move": self.move,
            "intent": self.intent,
            "hint": self.hint,
        }
        if self.barrier is not None:
            body["barrier"] = list(self.barrier)
        return body


@dataclass
class RevealedStep:
    """A step the opponent has revealed to us (nonce still withheld)."""

    step: int
    role: str
    move: str
    hint: str
    intent: str | None
    barrier: list[int] | None
    commit: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any], commit_hash: str) -> RevealedStep:
        return cls(
            step=int(payload.get("step", 0)),
            role=str(payload.get("role", "")),
            move=str(payload.get("move", "STAY")),
            hint=str(payload.get("hint", "")),
            # At reveal time the opponent MAY withhold the intent flag; it is
            # binding only once the nonce is disclosed at the final audit.
            intent=payload.get("intent"),
            barrier=payload.get("barrier"),
            commit=commit_hash,
        )
