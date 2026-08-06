"""Running a series and turning it into the four mandatory artifacts.

A *game* between two teams is a series of sub-games (six by default), and the
roles swap halfway through so neither side gets the easier half of the asymmetry
(:mod:`p2pchase.domain.roles` holds the rule and why it is derived, not agreed
move by move). That swap is the reason so little state carries across a
sub-game: each one gets
a fresh board, fresh beliefs and a fresh commit chain, while the declaration and
the running tally span the whole series.

This service owns that arc -- start the series, play each sub-game, write its
config and log, and close with a result report both teams can compare digest to
digest.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import constants
from ..domain import roles
from ..domain.crypto import commit
from ..domain.scoring import ScoreTable, SeriesTally, build_score_table
from ..infra.sysinfo import build_step0, collect_hardware, git_commit
from ..reports import artifacts
from ..runtime.local_match import run_local_match
from ..shared.paths import artifacts_dir
from ..shared.peer_config import PeerConfig

LOGGER = logging.getLogger(__name__)


#: Re-exported: the role rule lives in the domain because it is a rule, not a
#: service, and both the MCP handlers and the CLI have to derive the same answer
#: without importing a series runner. See :mod:`p2pchase.domain.roles` for why
#: the parity rule that used to live here disagreed with itself across peers.
roles_for_sub_game = roles.roles_for_sub_game


@dataclass
class SeriesResult:
    """Everything one finished series produced."""

    game_id: str
    game_uid: str
    outcomes: list[artifacts.SubGameOutcome] = field(default_factory=list)
    final_result: dict[str, Any] = field(default_factory=dict)
    tokens: dict[str, int] = field(default_factory=dict)
    paths: list[Path] = field(default_factory=list)


class MatchService:
    """Plays sub-games and writes their artifacts.

    Input:  a loaded :class:`PeerConfig` and the opponent's group id.
    Output: a :class:`SeriesResult` plus the JSON files on disk.
    Setup:  ``output_dir`` (defaults to ``artifacts/``), ``signing_secret``
            (signs the Step-0 hardware declaration, rule 24).
    """

    def __init__(self, config: PeerConfig, output_dir: Path | None = None,
                 signing_secret: str = "") -> None:
        self.config = config
        self.output_dir = Path(output_dir) if output_dir else artifacts_dir()
        self.signing_secret = signing_secret
        self.table: ScoreTable = build_score_table(config.shared)

    # ------------------------------------------------------------- identity
    def identity(self, mcp_url: str = "") -> artifacts.GroupIdentity:
        """This team's static declaration entry, hardware included."""
        return artifacts.GroupIdentity(
            group_id=self.config.group_id,
            group_name=self.config.group_name,
            members=self.config.members,
            repos=self.config.repos,
            mcp_servers={"url": mcp_url or self.config.public_url or
                         f"http://127.0.0.1:{self.config.my_port}/mcp"},
            llm_model=str(self.config.llm.get("model", "template")),
            hardware_spec=collect_hardware().as_dict(),
        )

    def step_zero(self, sub_game: int, role: str = "") -> dict[str, Any]:
        """Signed hardware declaration, committed as step 0 of every log.

        It is wrapped in a commit record like any other step, not written raw.
        Signing proves *we* declared it; committing proves we declared it
        *before* the match and never edited it afterwards -- which is the claim
        rule 24 actually needs, since a signature we control could be recomputed
        over softer hardware at any time.
        """
        payload = build_step0(
            group_name=self.config.group_name,
            sub_game_number=sub_game,
            llm_model=str(self.config.llm.get("model", "template")),
            signing_secret=self.signing_secret,
            role=role or self.config.role,
            group_id=self.config.group_id,
        )
        return commit(payload).audit_view()

    # ---------------------------------------------------------------- series
    def run_series(self, opponent_group: str, sub_games: int | None = None,
                   seed: int = 0) -> SeriesResult:
        """Play a full local series and write every artifact it produces."""
        count = sub_games or self.config.num_sub_games
        mine, theirs = self.config.group_id, opponent_group
        game_id = artifacts.make_game_id(mine, theirs)
        game_uid = artifacts.new_game_uid()
        started = artifacts.now_iso()

        names = artifacts.ArtifactSet(game_id=game_id, directory=self.output_dir)
        tally = SeriesTally(mine, theirs, tie_score=self.table.tie_score,
                            tie_rule=self.config.tie_rule(theirs))
        result = SeriesResult(game_id=game_id, game_uid=game_uid)
        result.paths.append(self._write_declaration(names, game_id, game_uid, theirs, started))

        for number in range(1, count + 1):
            # ``count``, not the configured length: the roles swap at the halfway
            # point of the series actually being played, so a two-sub-game
            # rehearsal swaps after one rather than pretending it is six.
            assignment = roles.roles_for_sub_game(number, mine, theirs, count,
                                                  self.config.role_convention(theirs))
            result.outcomes.append(self._play_one(names, game_id, game_uid, number,
                                                  theirs, tally, seed + number, result,
                                                  assignment))

        result.final_result = tally.finalise()
        result.tokens = {mine: sum(o.tokens.get(mine, 0) for o in result.outcomes),
                         theirs: sum(o.tokens.get(theirs, 0) for o in result.outcomes)}
        report = artifacts.build_result_artifact(game_id, game_uid, [mine, theirs],
                                         result.outcomes, result.final_result, result.tokens)
        result.paths.append(artifacts.write_json(names.result(), report))
        LOGGER.info("series %s complete: %s", game_id, result.final_result)
        return result

    def _write_declaration(self, names: artifacts.ArtifactSet, game_id: str, game_uid: str,
                           opponent: str, started: str) -> Path:
        """Write the pre-game declaration for both sides of a local rehearsal."""
        theirs = artifacts.GroupIdentity(
            group_id=opponent, group_name=opponent, members=[], repos={},
            mcp_servers={"url": self.config.opponent_url},
            llm_model="unknown", hardware_spec={},
        )
        payload = artifacts.build_declaration(
            game_id, game_uid, self.identity(), theirs,
            num_sub_games=self.config.num_sub_games,
            max_tokens_per_game=int(self.config.shared["network_and_league"]
                                    ["token_budget_per_series"]),
            started_at=started,
        )
        return artifacts.write_json(names.declaration(), payload)

    def _play_one(self, names: artifacts.ArtifactSet, game_id: str, game_uid: str, number: int,
                  opponent: str, tally: SeriesTally, seed: int, result: SeriesResult,
                  assignment: dict[str, str]) -> artifacts.SubGameOutcome:
        """Play one sub-game, write its config and both logs, and score it."""
        mine = self.config.group_id
        started = artifacts.now_iso()

        config_payload = artifacts.build_config_artifact(self.config.agreed_terms(), game_id,
                                                 game_uid, number, [mine, opponent])
        result.paths.append(artifacts.write_json(names.config(number), config_payload))

        # Whose group id labels which side follows the assignment rather than
        # always naming us the cop. Under the old parity rule those two agreed by
        # accident in odd sub-games and the log quietly misattributed the rest.
        i_am_cop = assignment[mine] == constants.ROLE_COP
        report, cop, thief = run_local_match(
            self.config.shared, cop_group=mine if i_am_cop else opponent,
            thief_group=opponent if i_am_cop else mine, sub_game=number,
            seed=seed, strategy_cfg=self.config.strategy,
            trash_talk_cfg=self.config.trash_talk, llm_cfg=self.config.llm,
        )
        ended = artifacts.now_iso()
        mine_side = cop if i_am_cop else thief
        audit = report.cop_audit if i_am_cop else report.thief_audit

        log = artifacts.build_log_artifact(
            game_id, game_uid, number, mine, assignment[mine], opponent, report.outcome,
            report.winner_role, [self.step_zero(number, assignment[mine]), *mine_side.records],
            started, ended, mine_side.talk.tokens_used, audit,
        )
        result.paths.append(artifacts.write_json(names.log(number), log))

        score = tally.record(assignment, report.outcome, self.table)
        return artifacts.SubGameOutcome(
            sub_game_number=number, roles=assignment, started_at=started, ended_at=ended,
            result=report.outcome,
            winner_group=next((g for g, r in assignment.items() if r == report.winner_role),
                              None),
            github_commit={mine: git_commit()},
            tokens={mine: mine_side.talk.tokens_used, opponent: 0},
            score=score, log_files={mine: names.log(number).name}, audit=audit,
        )
