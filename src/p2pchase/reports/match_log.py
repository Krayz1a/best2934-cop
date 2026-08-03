"""The per-sub-game disclosed log -- the input to the replay verifier (ch7.4).

A log is written once, at the end of a sub-game, and it is the only artifact
that contains nonces. That timing is the whole security argument: during play a
peer publishes commitments alone, so nothing about a move can be inferred from
its hash; after play the nonces are disclosed and every commitment becomes
independently checkable (rule 18).

``records`` are audit views -- payload, nonce and announced commitment for each
step, including the Step-0 hardware declaration, which is why ``steps`` counts
``len(records) - 1``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .. import constants as K
from .naming import TIMEZONE, links_block


def _duration_seconds(started_at: str, ended_at: str) -> float:
    """Elapsed match time, tolerating a clock that produced an unparsable stamp.

    A malformed timestamp must not be able to destroy a log that is otherwise
    cryptographically sound, so this degrades to 0.0 rather than raising.
    """
    try:
        started = datetime.fromisoformat(started_at)
        ended = datetime.fromisoformat(ended_at)
    except (TypeError, ValueError):
        return 0.0
    return round((ended - started).total_seconds(), 1)


def build_log_artifact(
    game_id: str,
    game_uid: str,
    sub_game_number: int,
    group_id: str,
    role: str,
    opponent_group_id: str,
    outcome: str,
    winner_role: str | None,
    records: list[dict[str, Any]],
    started_at: str,
    ended_at: str,
    tokens_total: int,
    audit: dict[str, Any],
    mutual: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One sub-game's full disclosed log.

    Input:  the peer's own commit/reveal records plus the match summary.
    Output: a JSON-ready dict the Replay Viewer can verify unaided.
    Setup:  ``mutual`` carries the opponent's counter-signature once the two
            teams have audited each other (rule 36); it starts unconfirmed.
    """
    return {
        "_schema": (
            "Per-sub-game match log consumed by the Replay Viewer for "
            "cryptographic verification: commit/reveal records, moves, hints, "
            "nonces and hashes."
        ),
        "schema_version": K.SCHEMA_VERSION,
        "game_id": game_id,
        "game_uid": game_uid,
        "links": links_block(game_id),
        "summary": {
            "sub_game_number": sub_game_number,
            "group_id": group_id,
            "role": role,
            "opponent_group_id": opponent_group_id,
            "result": outcome,
            "winner_role": winner_role,
            "steps": max(0, len(records) - 1),  # step 0 is the declaration
            "timezone": TIMEZONE,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_seconds": _duration_seconds(started_at, ended_at),
            "tokens_total": tokens_total,
            "audit": audit,
        },
        "records": records,
        "mutual_agreement": mutual or {
            "opponent_group_id": opponent_group_id,
            "sha256": "",
            "confirmed": False,
        },
    }
