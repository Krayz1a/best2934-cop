"""The ``TurnMessage`` -- gal-roy1's INTEROP.md section 4, in both directions.

One object carries a whole turn: the sealed commitment, the sentence, our
lagged trail, and whatever the rules compel us to declare openly. What it does
*not* carry is the point -- the sender's position and move are absent by design,
sealed in ``commit`` and proven only at the audit (I-5).

Two shapes matter beyond the obvious one.

**The nil turn.** ``{"step": 0, "sender": ..., "nil": true}`` with no commitment.
It exists so the turn token can be handed over without anybody moving, which is
what lets the cop move first in every sub-game while either side drives the
connection. A received nil turn must NOT advance the receiver's round counter --
their rule, and the right one: a round is a round because somebody acted in it,
and counting a handover would drift the two survival clocks apart by exactly one.

**The claim response.** A cop claims a cell; the thief must answer honestly
(rules 21, 22). It travels back in the *response* to ``submit_turn`` rather than
in the next turn message, because the claiming peer has to learn it won before
it decides whether there is a next turn at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..domain.protocol import WIRE_ROLE


@dataclass
class TurnMessage:
    """One peer's turn, as it travels. Parsed defensively; built exactly."""

    step: int
    sender: str
    commit: str = ""
    hint: str = ""
    scent_grid: dict[str, float] = field(default_factory=dict)
    barrier_placed: list[int] | None = None
    capture_claim: list[int] | None = None
    claim_response: dict[str, Any] | None = None
    win_claim: dict[str, Any] | None = None
    nil: bool = False

    @property
    def is_nil(self) -> bool:
        """A handover, not a move.

        Trusts the flag *and* the absence of a commitment, because the two say
        the same thing and a turn that set one without the other would be a bug
        we would rather not silently play through.
        """
        return bool(self.nil) or not self.commit

    def as_dict(self) -> dict[str, Any]:
        """Their field names, with the optional ones omitted rather than nulled."""
        if self.is_nil:
            return {"step": self.step, "sender": self.sender, "commit": None,
                    "hint": None, "scent_grid": {}, "nil": True}
        body: dict[str, Any] = {
            "step": self.step,
            "sender": self.sender,
            "commit": self.commit,
            "hint": self.hint,
            "scent_grid": dict(self.scent_grid),
        }
        for name, value in (("barrier_placed", self.barrier_placed),
                            ("capture_claim", self.capture_claim),
                            ("claim_response", self.claim_response),
                            ("win_claim", self.win_claim)):
            if value is not None:
                body[name] = value
        return body


def parse_turn(payload: dict[str, Any]) -> TurnMessage:
    """Read an incoming turn without trusting any of it.

    Every field is coerced and every absence is tolerated. A malformed turn from
    an opponent must produce a refusal we can explain, never an exception: an
    exception crosses MCP as an opaque transport failure and rule 6 charges both
    teams for the stall.
    """
    scent = payload.get("scent_grid") or {}
    return TurnMessage(
        step=int(payload.get("step", 0) or 0),
        sender=str(payload.get("sender", "")).upper(),
        commit=str(payload.get("commit") or ""),
        hint=str(payload.get("hint") or ""),
        scent_grid={str(k): float(v) for k, v in scent.items()},
        barrier_placed=_cell(payload.get("barrier_placed")),
        capture_claim=_cell(payload.get("capture_claim")),
        claim_response=payload.get("claim_response"),
        win_claim=payload.get("win_claim"),
        nil=bool(payload.get("nil", False)),
    )


def _cell(value: Any) -> list[int] | None:
    """A ``[row, col]`` pair, or ``None`` for anything that is not one."""
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    try:
        return [int(value[0]), int(value[1])]
    except (TypeError, ValueError):
        return None


def nil_turn(role: str, step: int = 0) -> dict[str, Any]:
    """The opening handover: pass the token without acting."""
    return TurnMessage(step=step, sender=WIRE_ROLE.get(role, role.upper()),
                       nil=True).as_dict()


def claim_response(cell: list[int], caught: bool) -> dict[str, Any]:
    """Rules 21-22, in their shape. Truthful because the audit will settle it."""
    return {"claim": [int(cell[0]), int(cell[1])], "caught": bool(caught)}
