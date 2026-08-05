"""The wire contract between two peers (book ch2, ch5, ch8).

Both agents are simultaneously an MCP server and an MCP client, so there is no
"the API" and no asymmetry to hide behind: whatever tools we expose, we must
also be willing to call on someone else. This module names those tools once, so
the server that implements them and the client that calls them cannot drift.

The turn is four messages, and the ordering is the entire security model:

    COMMIT  ->  ACK  ->  REVEAL  ->  APPLY

At COMMIT a peer publishes only ``sha256(payload || nonce)``. The move, the
hint and the truth/lie flag are all sealed inside and disclosed at REVEAL --
with the nonce still withheld, so nothing can be verified yet and nothing can be
retro-fitted either. Only at the end of the sub-game does FINAL_REVEAL disclose
every nonce at once, and the whole chain becomes checkable in one pass.

Withholding the nonce until then is what makes the scheme work. A peer that
revealed nonces per step would let its opponent verify each move immediately --
and, far worse, would let a dishonest opponent wait to see a verified move
before committing its own.
"""

from __future__ import annotations

from typing import Any

#: Tool names. Both peers must agree on these strings exactly.
TOOL_HELLO = "hello"
TOOL_NEGOTIATE = "negotiate"
TOOL_STEP0 = "declare_step0"
TOOL_COMMIT = "commit_step"
TOOL_ACK = "acknowledge_step"
TOOL_REVEAL = "reveal_step"
TOOL_SCENT = "sample_scent"
TOOL_FINAL_REVEAL = "final_reveal"
TOOL_AUDIT = "audit_result"
TOOL_AGREE = "agree_result"
TOOL_ABORT = "abort"

ALL_TOOLS: tuple[str, ...] = (
    TOOL_HELLO, TOOL_NEGOTIATE, TOOL_STEP0, TOOL_COMMIT, TOOL_ACK, TOOL_REVEAL,
    TOOL_SCENT, TOOL_FINAL_REVEAL, TOOL_AUDIT, TOOL_AGREE, TOOL_ABORT,
)


def ok(**fields: Any) -> dict[str, Any]:
    """A successful tool response."""
    return {"ok": True, **fields}


def error(reason: str, **fields: Any) -> dict[str, Any]:
    """A refusal. Never raises across the wire -- the caller must see why.

    An exception crossing MCP arrives as an opaque transport failure, which the
    opponent cannot distinguish from a crash. A structured refusal lets an
    honest peer fix its message and retry; rule 6 punishes both sides for a
    stalled sub-game, so ambiguity here is expensive for everyone.
    """
    return {"ok": False, "reason": reason, **fields}


def commit_payload(game_id: str, sub_game: int, step: int, group: str, role: str,
                   commitment: str) -> dict[str, Any]:
    """COMMIT: the hash alone. Nothing about the move is inferable from it."""
    return {
        "game_id": game_id,
        "sub_game_number": sub_game,
        "step": step,
        "sender_group": group,
        "sender_role": role,
        "commit": commitment,
    }


def reveal_payload(game_id: str, sub_game: int, step: int, group: str, role: str,
                   move: str, hint: str, barrier: list[int] | None,
                   intent: str | None = None,
                   capture_claim: list[int] | None = None) -> dict[str, Any]:
    """REVEAL: the move, the hint and any barrier -- but never the nonce.

    ``intent`` is optional here on purpose. A peer may withhold its truth/lie
    flag until the final audit; it is already sealed in the commitment, so
    withholding it changes nothing about what can be proved later.
    """
    body: dict[str, Any] = {
        "game_id": game_id,
        "sub_game_number": sub_game,
        "step": step,
        "sender_group": group,
        "sender_role": role,
        "move": move,
        "hint": hint,
        "barrier": list(barrier) if barrier else None,
    }
    if intent is not None:
        body["intent"] = intent
    if capture_claim is not None:
        # Rule 21: a cop that believes it has caught the thief must say so, and
        # say it truthfully. The claim names a cell -- our own -- so answering
        # it costs the thief nothing it did not already learn from our move.
        body["capture_claim"] = [int(capture_claim[0]), int(capture_claim[1])]
    return body


def scent_query(game_id: str, sub_game: int, step: int, cells: list[list[int]]) -> dict[str, Any]:
    """Ask the opponent for its pheromone intensity at specific cells.

    Sampling is pull-based and explicit so the trail stays *evidence* rather
    than a broadcast: a peer learns only about cells it thought to ask about,
    and the answer is unforgeable because the emitter computes it from the
    agreed kernel both sides fingerprinted before the match.
    """
    return {
        "game_id": game_id,
        "sub_game_number": sub_game,
        "step": step,
        "cells": [list(cell) for cell in cells],
    }


def final_reveal_payload(game_id: str, sub_game: int, group: str,
                         records: list[dict[str, Any]],
                         outcome: str = "") -> dict[str, Any]:
    """FINAL_REVEAL: the complete audit view, nonces included (rule 18).

    ``outcome`` is how the sender says the sub-game ended, and it is load-bearing
    for one case the wire cannot otherwise carry: a thief with no legal move is
    captured (rule 47), and only the thief can see that. Without the
    declaration the cop waits for a commitment that will never come and rule 6
    turns a won sub-game into a technical loss for both teams.

    Believing it is safe because the only side that can declare it is declaring
    against itself, and the disclosed chain arriving in the same message makes
    the claim checkable move by move.
    """
    return {
        "game_id": game_id,
        "sub_game_number": sub_game,
        "sender_group": group,
        "records": records,
        "outcome": outcome,
    }


def parse_capture_claim(payload: dict[str, Any]) -> list[int] | None:
    """The claimed cell from a REVEAL body, or ``None`` if no claim was made."""
    claim = payload.get("capture_claim")
    if claim is None:
        return None
    return [int(claim[0]), int(claim[1])]


def parse_reveal(payload: dict[str, Any]) -> tuple[str, str, list[int] | None]:
    """Extract ``(move, hint, barrier)`` from a REVEAL body, defensively."""
    move = str(payload.get("move", "STAY")).upper()
    hint = str(payload.get("hint", ""))
    barrier = payload.get("barrier")
    if barrier is not None:
        barrier = [int(barrier[0]), int(barrier[1])]
    return move, hint, barrier
