"""Artifact naming and file writing (book ch9.3.3, Appendix F Table 20).

Every match produces four files that must be identifiable months later and
across two independently written codebases. Two decisions make that work:

*Order-independent ids.* ``make_game_id`` sorts the two group names, so both
peers derive the same ``game_id`` without exchanging it. A match is the same
match whichever side you ask.

*Names derived, never invented.* Match-level files carry the game id; per-sub-game
files carry the sub-game number as well. Nothing is left to a caller's choice,
so two teams' artifact sets line up file for file when they audit each other.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

#: The league runs on Israel time; every timestamp in every artifact says so.
TIMEZONE = "Asia/Jerusalem"


def now_iso() -> str:
    """Current instant in ISO-8601 with an explicit UTC offset."""
    return datetime.now(UTC).isoformat()


def new_game_uid() -> str:
    """A globally unique id for one match, generated once by the initiator."""
    return str(uuid.uuid4())


def make_game_id(group_a: str, group_b: str) -> str:
    """Stable, order-independent match id so both peers derive the same name."""
    first, second = sorted([group_a, group_b])
    return f"{first}-vs-{second}"


def links_block(game_id: str) -> dict[str, Any]:
    """Cross-references between the four artifacts of one match."""
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
    """Write human-readable JSON and return the path.

    Indented and key-order-preserving on purpose: these files are read by a
    human auditor from the opposing team, not only by a parser. The canonical,
    sorted form used for hashing lives in
    :func:`~p2pchase.domain.crypto.canonical_json` and is a different thing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=False)
        handle.write("\n")
    return path


@dataclass
class ArtifactSet:
    """Filenames for one match, all derived from the game id (Table 20).

    Input:  ``game_id`` and a target directory.
    Output: a resolved path per artifact.
    Setup:  ``directory`` defaults to ``artifacts/`` beside the repository root.
    """

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

    def all_paths(self, sub_games: int) -> list[Path]:
        """Every file this match should produce -- used to check completeness."""
        paths = [self.declaration(), self.result()]
        for number in range(1, sub_games + 1):
            paths.extend([self.config(number), self.log(number)])
        return paths
