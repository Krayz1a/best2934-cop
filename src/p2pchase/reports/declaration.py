"""The pre-game declaration and the locked sub-game config (book ch5, ch9.3.3).

These are the two artifacts written *before* play, and both exist to remove
arguments afterwards.

The **declaration** is the immutable spine of a whole series: who is playing,
from which repositories, on what hardware, with which model and token cap.
Roles swap between sub-games, so no role and no sub-game number appear here --
anything that varies per sub-game belongs in the log and the result.

The **config artifact** is one sub-game's agreed parameters, locked with
``config_sha256``. Both peers must hold a byte-identical copy (rule 11); the
pre-game exchange compares the digest and refuses to play on any mismatch. The
digest covers the agreed terms only, not the derived naming metadata, which is
identical on both sides by construction anyway.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .. import constants as K
from ..domain.crypto import digest_payload
from .naming import TIMEZONE, links_block, now_iso


@dataclass
class GroupIdentity:
    """One team's static identity, as it appears in the declaration.

    Input:  the team's own facts -- name, members, repositories, endpoints.
    Output: :meth:`as_dict`, self-signed so any later edit is detectable.
    Setup:  ``signature`` may be supplied when replaying an existing artifact;
            left empty it is computed from the body.
    """

    group_id: str
    group_name: str
    members: list[str]
    repos: dict[str, str]
    mcp_servers: dict[str, str]
    llm_model: str
    hardware_spec: dict[str, Any]
    signature: str = ""

    def as_dict(self) -> dict[str, Any]:
        body = {
            "group_id": self.group_id,
            "group_name": self.group_name,
            "members": list(self.members),
            "repos": dict(self.repos),
            "mcp_servers": dict(self.mcp_servers),
            "llm_model": self.llm_model,
            "hardware_spec": dict(self.hardware_spec),
        }
        body["signature"] = self.signature or digest_payload(body)
        return body


def build_declaration(
    game_id: str,
    game_uid: str,
    group_1: GroupIdentity,
    group_2: GroupIdentity,
    num_sub_games: int = K.NUM_SUB_GAMES,
    max_tokens_per_game: int = K.TOKEN_BUDGET_PER_SERIES,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> dict[str, Any]:
    """Pre-game declaration: everything that does not change across the series."""
    return {
        "_schema": (
            "Static declaration for the WHOLE game (the full series of "
            "sub-games) between two teams: identity, members, repositories, "
            "MCP servers, hardware, model, agreed token cap and timings. "
            "Signed and locked before play (book ch5, Step-0)."
        ),
        "schema_version": K.SCHEMA_VERSION,
        "declaration_type": "pre_game_declaration",
        "game_id": game_id,
        "game_uid": game_uid,
        "links": links_block(game_id),
        "timezone": TIMEZONE,
        "game_started_at": started_at or now_iso(),
        "game_ended_at": ended_at,
        "num_sub_games": num_sub_games,
        "max_tokens_per_game": max_tokens_per_game,
        "groups": {"group_1": group_1.as_dict(), "group_2": group_2.as_dict()},
    }


def build_config_artifact(
    agreed: dict[str, Any],
    game_id: str,
    game_uid: str,
    sub_game_number: int,
    agreed_between: list[str],
) -> dict[str, Any]:
    """The agreed sub-game configuration, locked with ``config_sha256``."""
    body: dict[str, Any] = {
        "_schema": (
            "Agreed configuration for one sub-game. Values come from the "
            "binding parameter table (Appendix F). Both teams hold "
            "byte-identical copies and lock them via config_sha256."
        ),
        "schema_version": K.SCHEMA_VERSION,
        "agreed_between": sorted(agreed_between),
    }
    body.update(agreed)
    body["game_id"] = game_id
    body["game_uid"] = game_uid
    body["sub_game_number"] = sub_game_number
    body["links"] = links_block(game_id)
    body["config_name"] = f"config_{game_id}_g{sub_game_number:02d}.json"
    body["config_sha256"] = digest_payload(agreed)
    return body
