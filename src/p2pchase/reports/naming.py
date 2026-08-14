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

import hashlib
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
    """A random uid, for a match that has no agreed terms to derive one from.

    Kept for the local rehearsal and the solo paths, which have no opponent to
    agree with and therefore nothing to derive from. **A networked match must
    use :func:`derive_game_uid` instead** -- see the warning there.
    """
    return str(uuid.uuid4())


def derive_game_uid(terms: dict[str, Any], group_a: str, group_b: str) -> str:
    """The uid both peers reach independently, with no round-trip.

    ``UUID(SHA256(canonical(terms) + "|" + "|".join(sorted(pair)))[:16])``, the
    kit's CORE construction (SPEC section 4, ``vectors/game_uid.json``). Both
    sides sort the pair, so neither has to be told whose name comes first.

    We shipped ``uuid4()`` here until 2026-08-14, and the friendly against
    imreeyal is what exposed it: their report carried
    ``0d98626a-7369-b854-e473-3df1898d45f1`` and ours carried
    ``f8e9733a-7665-4044-a392-69640a28ac64``, for the same six sub-games, from
    identical terms. Theirs is not even a version-4 uuid -- the version nibble
    is ``b`` -- which is the tell that it was derived while ours was rolled.

    A uid is what joins the four artifacts of one match, so two uids means the
    lecturer receives two matches that cannot be joined, from two teams who
    both played correctly. anrbj666 put the cost precisely on league issue #49:
    a mismatch found before play is a five-minute fix, and found at settlement
    it voids the match for both teams under rule 35.
    """
    from ..domain.crypto import canonical_json  # local: naming is imported early
    preimage = canonical_json(terms) + "|" + "|".join(sorted([group_a, group_b]))
    return str(uuid.UUID(bytes=hashlib.sha256(preimage.encode("utf-8")).digest()[:16]))


def make_game_id(group_a: str, group_b: str) -> str:
    """Stable, order-independent match id so both peers derive the same name."""
    first, second = sorted([group_a, group_b])
    return f"{first}-vs-{second}"


def opponent_in_game_id(game_id: str, mine: str) -> str:
    """The other half of a ``<a>-vs-<b>`` id, or ``""`` if it is not one.

    The inverse of :func:`make_game_id`, and it lives beside it so the two
    cannot drift. Worth having because the pairing terms a peer runs -- which
    scent model, which role convention -- are keyed by opponent, and a served
    peer learns the game id long before anyone hands it an opponent name.

    Empty rather than a guess when the id has any other shape, **and when
    neither half is us**. Falling back means running the book's model under the
    first-half convention, which is what we did before pairings existed;
    guessing means running terms one opponent agreed against a different
    opponent who never did.

    That second condition is not defensive padding. An id we are not named in
    is one we do not understand -- a rehearsal id, a renamed group, a peer that
    built the name from something other than group ids -- and answering it with
    "the half that is not ours" requires knowing which half that is.
    """
    halves = str(game_id).split("-vs-")
    if len(halves) != 2 or str(mine) not in halves:
        return ""
    return halves[1] if halves[0] == str(mine) else halves[0]


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
