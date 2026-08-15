"""Artifacts for a *networked* sub-game (rules 20, 32-35, 49, 53).

The local rehearsal writes its four artifacts because one process plays the
whole series. A real league match does not work that way: each sub-game is its
own process against a live opponent, and until now that path printed its
outcome to the terminal and wrote nothing. A match that leaves no artifacts
cannot be replayed by the opponent, cannot be audited, and cannot be reported --
which is three separate disqualifications, so this service exists to close them.

Each finished sub-game writes its config and log, then the series result is
rebuilt from every log on disk (see :mod:`..reports.series_assembly`). Running
sub-game 2 therefore repairs a result that sub-game 1 left incomplete, and a
crashed run costs only the sub-game it was playing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..domain.core_terms import core_terms
from ..domain.scoring import build_score_table
from ..infra.sysinfo import collect_hardware, git_commit
from ..reports import artifacts
from ..reports.naming import opponent_in_game_id
from ..reports.series_assembly import assemble_series
from ..reports.standings import standings_block
from ..shared.paths import artifacts_dir, sibling_artifacts_dir
from ..shared.peer_config import PeerConfig
from . import settlement_report

LOGGER = logging.getLogger(__name__)


class NetworkArtifactService:
    """Writes the four artifacts of a live match, one sub-game at a time.

    Input:  a loaded :class:`PeerConfig` and, per sub-game, what the peer
            runner came back with.
    Output: `config_*`, `log_*`, `declaration_*` and `result_*` JSON on disk.
    Setup:  ``output_dir`` defaults to ``artifacts/``.
    """

    def __init__(self, config: PeerConfig, output_dir: Path | None = None,
                 counted: bool = False) -> None:
        self.config = config
        self.counted = counted
        self.output_dir = Path(output_dir) if output_dir else artifacts_dir(counted)
        self.table = build_score_table(config.shared)

    @classmethod
    def for_opponent(cls, config: PeerConfig, opponent: str,
                     output_dir: Path | None = None) -> NetworkArtifactService:
        """Build the service with the directory this pairing's status requires.

        The counted flag is read from the pairing rather than passed in, so a
        caller cannot write a counted series into the friendly directory by
        forgetting an argument. That is the whole point of the separation:
        see :func:`~p2pchase.shared.paths.artifacts_dir`.
        """
        counted, _sign_off = config.counted_series(opponent)
        return cls(config, output_dir, counted=bool(counted))

    # ------------------------------------------------------------- identity
    def _identity(self, handshake: dict[str, Any]) -> artifacts.GroupIdentity:
        """The opponent as they described themselves at the handshake.

        Taken from what they published rather than from anything we assume: a
        declaration that quietly invented the opponent's details would be a
        declaration neither team could sign.
        """
        return artifacts.GroupIdentity(
            group_id=str(handshake.get("group_id", "unknown")),
            group_name=str(handshake.get("group_name", handshake.get("group_id", "unknown"))),
            members=list(handshake.get("members", [])),
            repos=dict(handshake.get("repos", {})),
            mcp_servers={"url": str(handshake.get("mcp_url", self.config.opponent_url))},
            llm_model=str(handshake.get("llm_model", "unknown")),
            hardware_spec=dict(handshake.get("hardware_spec", {})),
        )

    def _mine(self, mcp_url: str = "") -> artifacts.GroupIdentity:
        return artifacts.GroupIdentity(
            group_id=self.config.group_id, group_name=self.config.group_name,
            members=self.config.members, repos=self.config.repos,
            mcp_servers={"url": mcp_url or self.config.public_url or ""},
            llm_model=str(self.config.llm.get("model", "template")),
            hardware_spec=collect_hardware().as_dict(),
        )

    # ---------------------------------------------------------- declaration
    def ensure_declaration(self, names: artifacts.ArtifactSet, game_id: str,
                           handshake: dict[str, Any], started_at: str) -> tuple[str, Path]:
        """Write the declaration once per game and return its ``game_uid``.

        The uid has to be stable across the separate processes that play the
        sub-games, so the first one mints it and the rest read it back. Minting
        a fresh uid per sub-game would split one match into several in the
        lecturer's records.
        """
        path = names.declaration()
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            return str(existing.get("game_uid", "")), path
        game_uid = self.game_uid_for(game_id)
        payload = artifacts.build_declaration(
            game_id, game_uid, self._mine(), self._identity(handshake),
            num_sub_games=self.config.num_sub_games,
            max_tokens_per_game=int(self.config.shared["network_and_league"]
                                    ["token_budget_per_series"]),
            started_at=started_at,
        )
        return game_uid, artifacts.write_json(path, payload)

    # -------------------------------------------------------------- writing
    def record_sub_game(self, game_id: str, sub_game: int, role: str, opponent: str,
                        outcome: Any, started_at: str, ended_at: str, tokens: int,
                        handshake: dict[str, Any] | None = None,
                        step_zero: dict[str, Any] | None = None,
                        declared_sub_games: list[int] | None = None,
                        declaration_keys: list[list[str]] | None = None) -> list[Path]:
        """Write one sub-game's config and log, then refresh the series result."""
        names = artifacts.ArtifactSet(game_id=game_id, directory=self.output_dir)
        game_uid, declaration = self.ensure_declaration(names, game_id, handshake or {},
                                                        started_at)
        written = [declaration]

        config_payload = artifacts.build_config_artifact(
            self.config.agreed_terms(), game_id, game_uid, sub_game,
            [self.config.group_id, opponent])
        written.append(artifacts.write_json(names.config(sub_game), config_payload))

        records = [step_zero, *outcome.records] if step_zero else list(outcome.records)
        log = artifacts.build_log_artifact(
            game_id, game_uid, sub_game, self.config.group_id, role, opponent,
            outcome.outcome, self.table.winner_role(outcome.outcome), records,
            started_at, ended_at, tokens, dict(outcome.opponent_audit),
            steps=int(getattr(outcome, "steps", 0) or 0),
            declared_sub_games=declared_sub_games,
            declaration_keys=declaration_keys,
        )
        written.append(artifacts.write_json(names.log(sub_game), log))
        result_path = self.refresh_result(game_id, game_uid, opponent)
        written.append(result_path)
        # Rule 32: the agent reports, not the operator. Fires only for a
        # counted pairing, only once the signed number of sub-games is on disk,
        # and only once -- see :mod:`.settlement_report`.
        settlement_report.fire_if_settled(self.config, opponent, result_path,
                                          self.counted)
        LOGGER.info("sub-game %d artifacts written under %s", sub_game, self.output_dir)
        return written

    def game_uid_for(self, game_id: str) -> str:
        """The match uid, derived from the agreed terms rather than rolled.

        Both peers reach this number independently from the flat fourteen and
        the sorted group pair, so the four artifacts of one match join up
        across two codebases. We rolled a ``uuid4()`` here until the imreeyal
        friendly on 2026-08-14 put their derived uid beside our random one in
        two reports describing the same six sub-games.

        Falls back to a random uid only when the game id does not name us and
        an opponent -- a rehearsal, a renamed group -- where there is no agreed
        pairing to derive from and nobody on the other side to disagree with.
        """
        opponent = opponent_in_game_id(game_id, self.config.group_id)
        if not opponent:
            return artifacts.new_game_uid()
        return artifacts.derive_game_uid(core_terms(self.config.shared),
                                         self.config.group_id, opponent)

    # --------------------------------------------------------------- result
    def series_logs(self, game_id: str) -> list[dict[str, Any]]:
        """Every log of this series, from *both* of the team's repositories.

        Rule 41 puts our cop and our thief in separate repositories, and a
        six-sub-game series alternates roles -- so three logs land here and
        three land in the sibling. Globbing only this directory produced two
        result artifacts, each internally consistent, each signed, and each
        naming the *opposite* winner: the cop repo settled g01/g03/g05 as
        imreeyal 30-15 while the thief repo settled g02/g04/g06 as best2934
        30-15, when the series was in fact a 45-45 tie. Filing either one is
        the rule-35 contradiction, and it is only visible once the two halves
        disagree -- which is to say, on a close series, at the settlement, too
        late. Found by the imreeyal friendly on 2026-08-14, which is precisely
        what they insisted the friendly was for.

        Logs are keyed on ``(sub_game_number, role)``, NOT on the filename.
        Keying on the filename was the same bug wearing the other repository's
        clothes. Against imreeyal the numbering happened to be globally
        disjoint -- cop 1/3/5, thief 2/4/6 -- so no two files shared a name and
        the merge worked by luck. Against gal-roy1 *both* repositories numbered
        from ``g01``, so ``log_..._g01.json`` existed in each, naming two
        different sub-games; the dict collapsed them and our cop's eight
        silently overwrote our thief's first eight. The result artifact then
        claimed we played police in all eight sub-games of a series whose roles
        must swap -- impossible on its face, and produced without one warning.
        Found 2026-08-15 while preparing to designate that series counted.

        The role is what makes the key unique, because a sub-game is played
        from exactly one repository and therefore in exactly one role. A
        genuine duplicate -- same number AND same role in both directories --
        is a stale or hand-copied file rather than a real disagreement, and
        there our own directory still wins, so the outcome stays deterministic.
        """
        found: dict[tuple[int, str, str], dict[str, Any]] = {}
        directories = [d for d in (sibling_artifacts_dir(self.counted), self.output_dir) if d]
        for directory in directories:  # ours last, so ours overwrites theirs
            for path in sorted(Path(directory).glob(f"log_{game_id}_g*.json")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["_filename"] = path.name
                summary = payload.get("summary", {})
                number = int(summary.get("sub_game_number", 0) or 0)
                role = str(summary.get("role", ""))
                # A log with no number and no role is malformed rather than a
                # sub-game, so it falls back to the filename: merging every
                # such file into one key would drop data to "fix" a collision,
                # which is the failure this method exists to prevent.
                found[(number, role, "" if number and role else path.name)] = payload
        return [found[key] for key in sorted(found)]

    def refresh_result(self, game_id: str, game_uid: str, opponent: str) -> Path:
        """Rebuild `result_<game_id>.json` from every log this match has produced."""
        names = artifacts.ArtifactSet(game_id=game_id, directory=self.output_dir)
        logs = self.series_logs(game_id)

        mine = self.config.group_id
        outcomes, final_result, tokens = assemble_series(
            logs, mine, opponent, self.table, git_commit(),
            self.config.tie_rule(opponent), self.config.role_convention(opponent))
        counted, _sign_off = self.config.counted_series(opponent)
        report = artifacts.build_result_artifact(
            game_id, game_uid, [mine, opponent], outcomes, final_result, tokens,
            repositories=self.repositories(game_id, opponent),
            league=artifacts.league_block(counted, _sign_off),
            standings=standings_block(
                mine, opponent, counted,
                # Their declared count, recorded by the operator from what they
                # told us (rule 37 makes each team declare its own). Never
                # guessed: a number we invent for another team is a false
                # declaration in *their* column of the lecturer's standings.
                int(self.config.pairing(opponent).get("opponent_counted_games", 0)),
                # The ledger is team-level, so it is read from the friendly
                # root whatever posture this series has -- otherwise a counted
                # series counts itself out of its own directory and a friendly
                # cannot see it at all.
                final_result.get("winner_group"), artifacts_dir()),
            headline_digest=self.config.headline_digest(opponent))
        return artifacts.write_json(names.result(), report)

    def repositories(self, game_id: str, opponent: str) -> dict[str, dict[str, str]]:
        """Both teams' cop and thief repositories -- four links, rule 49."""
        theirs: dict[str, str] = {}
        declaration = artifacts.ArtifactSet(game_id=game_id,
                                            directory=self.output_dir).declaration()
        if declaration.exists():
            groups = json.loads(declaration.read_text(encoding="utf-8")).get("groups", {})
            for entry in groups.values():
                if entry.get("group_id") == opponent:
                    theirs = dict(entry.get("repos", {}))
        return {self.config.group_id: dict(self.config.repos), opponent: theirs}
