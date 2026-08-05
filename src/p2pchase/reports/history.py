"""How many counted games we have actually played (rules 37, 38, 52).

Rule 37 makes a team declare its true number of games at the start of every
game, and rule 38 sanctions declaring it falsely -- so the number must not be
something anyone types from memory into a handshake.

The obvious implementation is to count the result artifacts on disk, and it is
wrong. We tried it: this repository's ``artifacts/`` holds finished results
against ``rival999`` and ``test1234``, both invented during development, and
counting files declared **two** counted games to a real opponent before we had
played one. An automatic false declaration is worse than a manual one, because
nobody is in a position to notice it.

The distinction a file cannot carry is that "counted" is not a property of a
game we played, it is an *agreement between two teams* (rule 52: exactly one
game per pairing counts, warm-ups are unlimited). So it is recorded where it is
made -- deliberately, once per opponent -- and the artifacts are then used to
check that record rather than to generate it. :func:`discrepancies` is what
makes the ledger falsifiable: an opponent claimed but never played, or played
and quietly dropped, shows up as a named problem instead of a silent number.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from ..shared.paths import artifacts_dir

LOGGER = logging.getLogger(__name__)

LEDGER_NAME = "counted_games.json"
RESULT_GLOB = "result_*.json"


def ledger_path(directory: Path | None = None) -> Path:
    return (directory or artifacts_dir()) / LEDGER_NAME


def counted_opponents(directory: Path | None = None) -> list[str]:
    """The opponents we have agreed a counted game with, in the order agreed."""
    path = ledger_path(directory)
    if not path.exists():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        LOGGER.warning("the counted-games ledger at %s will not parse", path)
        return []
    if not isinstance(entries, list):
        return []
    return [str(e) for e in entries if isinstance(e, str) and e]


def counted_games_played(directory: Path | None = None) -> int:
    """The number rule 37 asks us to declare."""
    return len(counted_opponents(directory))


def record_counted_game(opponent: str, directory: Path | None = None) -> list[str]:
    """Declare one counted game against ``opponent``. Idempotent by rule 52.

    Re-recording the same opponent is a no-op rather than an error: rule 52
    allows exactly one counted game per pairing, so the second call is either a
    mistake or a retry, and neither should inflate the count.
    """
    directory = directory or artifacts_dir()
    entries = counted_opponents(directory)
    if opponent in entries:
        return entries
    entries.append(opponent)
    directory.mkdir(parents=True, exist_ok=True)
    ledger_path(directory).write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    return entries


def _opponents_with_results(us: str, directory: Path) -> set[str]:
    """Every group named in a result artifact that is not us."""
    found: set[str] = set()
    for path in sorted(directory.glob(RESULT_GLOB)):
        try:
            groups = json.loads(path.read_text(encoding="utf-8")).get("groups")
        except (OSError, ValueError):
            LOGGER.warning("ignoring unreadable result artifact %s", path.name)
            continue
        if isinstance(groups, list):
            found |= {str(g) for g in groups if isinstance(g, str) and g and g != us}
    return found


def discrepancies(us: str, directory: Path | None = None) -> list[str]:
    """Where the ledger and the artifacts disagree, in plain words.

    Only the first kind is a rule violation. A result with no ledger entry is
    the normal shape of a warm-up or a development run, so it is reported as
    information and not as a fault -- but it is reported, because a counted
    game someone forgot to record looks exactly the same from here.
    """
    directory = directory or artifacts_dir()
    if not directory.is_dir():
        return []
    claimed = set(counted_opponents(directory))
    played = _opponents_with_results(us, directory)
    problems = [f"declared a counted game against {name!r} with no result artifact to show for it"
                for name in sorted(claimed - played)]
    problems += [f"a result exists against {name!r} that is not declared as counted "
                 f"(expected for a warm-up)" for name in sorted(played - claimed)]
    return problems
