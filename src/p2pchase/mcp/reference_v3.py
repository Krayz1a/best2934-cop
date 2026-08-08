"""The reference-v3 wire: validation and translation, with no transport in it.

The dialect imreeyal, anrbj666 and uoh-sqak all speak (kit
``vectors/turn_message.json``, SPEC section 7.5). Four tools, of which we need
three, and a shape close enough to our own that the whole gap is a rename, a
required ``timestamp``, and the absence of a nil turn.

Two things here are not cosmetic.

**Validation happens before any state change.** The vector is explicit that an
inbound turn is adversarial input and that a partially applied bad turn cannot
be rolled back -- under rule 35 a self-inflicted protocol fault zeroes *both*
teams. So :func:`refuse_turn` decides on the raw dict, and nothing touches a
session until it has returned "".

**The refusal strings are the vector's verdicts, verbatim.** Not paraphrases:
the kit publishes seven cases with an expected verdict each, so returning the
same text lets the vector be the oracle rather than something a test restates.
A restated expectation is a second copy that can drift from the thing it checks,
which is the failure this whole evening was made of.

The argument-name asymmetry lives in the binding, not here: ``negotiate``,
``receive_turn`` and ``receive_control`` take ``message``, ``submit_audit``
takes ``payload``. It is the reference's own inconsistency and copying it is the
whole point -- a peer that "tidies" it is unreachable.
"""

from __future__ import annotations

import re
from typing import Any

from ..domain.protocol import WIRE_ROLE

#: Lowercase only. The commitment is compared as a string, so case is divergence.
HEX64 = re.compile(r"\A[0-9a-f]{64}\Z")

SENDERS = ("police", "thief")

#: Their names for the four optional fields; identical to ours, happily.
OPTIONAL = ("barrier_placed", "capture_claim", "claim_response", "win_claim")


def refuse_turn(message: Any) -> str:
    """Why this TurnMessage may not be applied, or ``""`` if it may.

    Checked in the vector's own order so a message failing two rules reports the
    same one the kit reports.
    """
    if not isinstance(message, dict):
        return "message: required object"
    step = message.get("step")
    if not isinstance(step, int) or isinstance(step, bool) or step < 0:
        return "step: required non-negative int"
    if message.get("sender") not in SENDERS:
        return "sender: required 'police' or 'thief'"
    if not isinstance(message.get("hint", ""), str):
        return "hint: required str"
    grid = message.get("smell_grid")
    if not isinstance(grid, dict) or not _grid_is_numeric(grid):
        return "smell_grid: required dict of 'r,c' -> number"
    commit = message.get("commit")
    if not isinstance(commit, str) or not HEX64.match(commit):
        return "commit: required 64-char lowercase hex"
    timestamp = message.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp:
        return "timestamp: required non-empty str"
    return ""


def _grid_is_numeric(grid: dict[Any, Any]) -> bool:
    """Every intensity a real number -- a stringified one poisons the physics.

    ``bool`` is excluded deliberately. It is an ``int`` in Python, so ``True``
    would pass a numeric check and then read as an intensity of 1.0, which is a
    silently wrong trail rather than a refused message.
    """
    return all(isinstance(value, (int, float)) and not isinstance(value, bool)
               for value in grid.values())


def refuse_audit(payload: Any) -> str:
    """Why this AuditPayload may not be applied, or ``""`` if it may."""
    if not isinstance(payload, dict):
        return "payload: required object"
    if payload.get("sender") not in SENDERS:
        return "sender: required 'police' or 'thief'"
    if not isinstance(payload.get("records"), list):
        return "records: required list of sealed records"
    if not isinstance(payload.get("result_claim", ""), str):
        return "result_claim: required str"
    return ""


def to_internal(message: dict[str, Any]) -> dict[str, Any]:
    """Their TurnMessage -> the payload our own turn loop already accepts.

    Only three things actually move: ``smell_grid`` becomes ``scent_grid``,
    ``sender`` becomes our uppercase wire role, and ``timestamp`` is dropped
    because nothing downstream reads it. Unknown keys are dropped with it --
    the vector requires us to tolerate them, which means ignore, not forward.
    """
    turn: dict[str, Any] = {
        "step": int(message["step"]),
        "sender": WIRE_ROLE.get(str(message["sender"]), str(message["sender"]).upper()),
        "commit": str(message["commit"]),
        "hint": str(message.get("hint", "")),
        "scent_grid": {str(k): float(v) for k, v in message["smell_grid"].items()},
    }
    for name in OPTIONAL:
        value = message.get(name)
        if value is not None:
            turn[name] = value
    return turn


def from_internal(turn: dict[str, Any], timestamp: str) -> dict[str, Any]:
    """Our turn -> their TurnMessage.

    ``timestamp`` is passed in rather than read from a clock so this stays pure
    and so the caller cannot forget it: the field is decorative and its absence
    is a hard refusal, which is the single most likely way to have every one of
    our turns rejected. The kit's own sparring peer sends ``""`` and is refused
    by every conformant receiver, so this is not a hypothetical.

    A nil turn cannot be expressed. Their wire has no step-0 turn at all, and
    inventing one would be refused for a missing commitment -- our opener
    against a reference-v3 peer has to be a real move at step 1.
    """
    sender = str(turn.get("sender", "")).lower()
    message: dict[str, Any] = {
        "step": int(turn.get("step", 0) or 0),
        "sender": sender if sender in SENDERS else "police",
        "hint": str(turn.get("hint") or ""),
        "smell_grid": {str(k): float(v) for k, v in (turn.get("scent_grid") or {}).items()},
        "commit": str(turn.get("commit") or ""),
        "timestamp": timestamp,
    }
    for name in OPTIONAL:
        message[name] = turn.get(name)
    return message


def audit_from_records(sender: str, records: list[dict[str, Any]],
                       result_claim: str) -> dict[str, Any]:
    """Our disclosed chain -> their AuditPayload.

    ``result_claim`` is what we believe the sub-game ended as; their vector is
    clear that the opponent's audit settles it and the claim never does.
    """
    role = str(sender).lower()
    return {"sender": role if role in SENDERS else "police",
            "records": list(records),
            "result_claim": str(result_claim)}
