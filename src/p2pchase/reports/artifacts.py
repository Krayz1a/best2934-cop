"""Facade over the four mandatory JSON artifacts (book ch9.3.3, Table 20).

Every match produces four files, all sharing one ``game_uid`` and named from the
``game_id`` so files from different matches can never be confused:

  ``declaration_<game_id>.json``      everything that does NOT change across the
                                      series -- teams, members, repos, MCP URLs,
                                      hardware, model, token cap, start/end times
  ``config_<game_id>_g<NN>.json``     the agreed, cryptographically locked
                                      parameters for one sub-game
  ``log_<game_id>_g<NN>.json``        step-by-step commit/reveal record, the
                                      input to the replay verifier
  ``result_<game_id>.json``           the final report e-mailed to the lecturer

Each builder lives in its own module; this file is the single import point.
"""

from __future__ import annotations

from ..domain.crypto import digest_payload
from .declaration import GroupIdentity, build_config_artifact, build_declaration
from .league import league_block
from .match_log import build_log_artifact
from .naming import (
    TIMEZONE,
    ArtifactSet,
    derive_game_uid,
    links_block,
    make_game_id,
    new_game_uid,
    now_iso,
    write_json,
)
from .result import SubGameOutcome, build_result_artifact

__all__ = [
    "TIMEZONE",
    "ArtifactSet",
    "GroupIdentity",
    "SubGameOutcome",
    "build_config_artifact",
    "build_declaration",
    "build_log_artifact",
    "build_result_artifact",
    "digest_payload",
    "league_block",
    "links_block",
    "make_game_id",
    "derive_game_uid",
    "new_game_uid",
    "now_iso",
    "write_json",
]
