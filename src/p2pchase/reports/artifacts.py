"""The four mandatory JSON artifacts (book ch9.3.3, Appendix F Table 20).

Every match produces four files, all sharing one ``game_uid`` and named from the
``game_id`` so files from different matches can never be confused:

  declaration_<game_id>.json        everything that does NOT change across the
                                    series -- teams, members, repos, MCP URLs,
                                    hardware, model, token cap, start/end times
  config_<game_id>_g<NN>.json       the agreed, cryptographically locked
                                    parameters for one sub-game
  log_<game_id>_g<NN>.json          step-by-step commit/reveal record, the input
                                    to the replay verifier
  result_<game_id>.json             the final report e-mailed to the lecturer

The result file is the binding one. Rule 34: it must be sent as an attached JSON
file, never as free text -- a plaintext report is rejected and scores zero. Rule
35: BOTH teams must send their own copy and they must agree; a missing or
contradicting report voids the match for both sides.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .. import constants as K
from ..domain.crypto import digest_payload, mutual_agreement_hash

TIMEZONE = "Asia/Jerusalem"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_game_uid() -> str:
    return str(uuid.uuid4())


def make_game_id(group_a: str, group_b: str) -> str:
    """Stable, order-independent match id so both peers derive the same name."""
    first, second = sorted([group_a, group_b])
    return f"{first}-vs-{second}"


def links_block(game_id: str) -> dict[str, Any]:
    return {
        "_remark": (
            "Logical roles, NOT fixed filenames. Match-level files "
            "(declaration, result) are named <role>_<game_id>.json; per-sub-game "
            "files (config, log) are named <role>_<game_id>_g<NN>.json."
        ),
        "declaration": f"declaration_{game_id}.json",
        "config": f"config_{game_id}_g<NN>.json",
        "log": f"log_{game_id}_g<NN>.json",
        "result": f"result_{game_id}.json",
    }


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    """Write canonical, human-readable JSON and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=False)
        handle.write("\n")
    return path


@dataclass
class GroupIdentity:
    """One team's static identity, as it appears in the declaration."""

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
    """Pre-game declaration: the immutable spine of the whole match.

    Roles swap between sub-games, so no role and no sub-game number appear
    here -- anything that varies per sub-game lives in the log and result.
    """
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
    """The agreed sub-game configuration, locked with ``config_sha256``.

    Both peers must hold a byte-identical copy (rule 11); the pre-game exchange
    compares this digest and refuses to play on any mismatch.
    """
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
    # The digest covers the agreed terms only -- not the naming metadata, which
    # is derived and therefore identical on both sides by construction.
    body["config_sha256"] = digest_payload(agreed)
    return body


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
    """One sub-game's full disclosed log, for the replay verifier.

    ``records`` are audit views -- payload, nonce and announced commit for every
    step, including the Step-0 hardware declaration. Nonces appear here because
    a log is only published after the match ends (rule 18).
    """
    started = datetime.fromisoformat(started_at)
    ended = datetime.fromisoformat(ended_at)
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
            "duration_seconds": round((ended - started).total_seconds(), 1),
            "tokens_total": tokens_total,
            "audit": audit,
        },
        "records": records,
        "mutual_agreement": mutual or {"opponent_group_id": opponent_group_id,
                                       "sha256": "", "confirmed": False},
    }


@dataclass
class SubGameOutcome:
    """One finished sub-game, as it appears in the result report."""

    sub_game_number: int
    roles: dict[str, str]
    started_at: str
    ended_at: str
    result: str
    winner_group: str | None
    github_commit: dict[str, str]
    tokens: dict[str, int]
    score: dict[str, int]
    log_files: dict[str, str]
    audit: dict[str, Any]
    tie: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "sub_game_number": self.sub_game_number,
            "roles": self.roles,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "result": self.result,
            "winner_group": self.winner_group,
            "tie": self.tie,
            "github_commit": self.github_commit,
            "tokens": self.tokens,
            "score": self.score,
            "log_files": self.log_files,
            "audit": self.audit,
        }


def build_result_artifact(
    game_id: str,
    game_uid: str,
    groups: list[str],
    sub_games: list[SubGameOutcome],
    final_result: dict[str, Any],
    tokens_total_series: dict[str, int],
    confirmed: bool = False,
) -> dict[str, Any]:
    """The binding final report e-mailed to the lecturer.

    The ``mutual_agreement.sha256`` is the fingerprint both teams compute over
    the agreed outcome. Because each side sends its own copy, two matching
    digests prove the teams agreed; a mismatch exposes a contradicting report,
    which rule 35 punishes by voiding the match for both.
    """
    summary = {
        "game_id": game_id,
        "game_uid": game_uid,
        "groups": sorted(groups),
        "sub_games": [sg.as_dict() for sg in sub_games],
        "final_result": final_result,
    }
    body = {
        "_schema": (
            "Summary and final result for the WHOLE game (all sub-games) "
            "between two teams: per-sub-game scores and the aggregate outcome "
            "used to build the league standings. Both teams must agree on this "
            "result and each sends its own copy to the lecturer (book ch9)."
        ),
        "schema_version": K.SCHEMA_VERSION,
        "report_type": "final_game_result",
        "game_id": game_id,
        "game_uid": game_uid,
        "links": links_block(game_id),
        "timezone": TIMEZONE,
        "groups": sorted(groups),
        "num_sub_games": len(sub_games),
        "sub_games": [sg.as_dict() for sg in sub_games],
        "final_result": {**final_result, "tokens_total_series": tokens_total_series},
        "mutual_agreement": {
            "sha256": mutual_agreement_hash(summary),
            "confirmed": confirmed,
        },
    }
    return body


@dataclass
class ArtifactSet:
    """Filenames for one match, all derived from the game id (Table 20)."""

    game_id: str
    directory: Path = field(default_factory=lambda: Path("artifacts"))

    def declaration(self) -> Path:
        return self.directory / f"declaration_{self.game_id}.json"

    def config(self, sub_game: int) -> Path:
        return self.directory / f"config_{self.game_id}_g{sub_game:02d}.json"

    def log(self, sub_game: int) -> Path:
        return self.directory / f"log_{self.game_id}_g{sub_game:02d}.json"

    def result(self) -> Path:
        return self.directory / f"result_{self.game_id}.json"
