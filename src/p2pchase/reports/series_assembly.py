"""Rebuild a series result from the sub-game logs already on disk.

A networked match is played one sub-game per process: the operator runs
``p2pchase play`` for sub-game 1, then again for sub-game 2, and each run exits
when its sub-game ends. Nothing survives in memory between them, so the series
result cannot be accumulated in a variable the way the local rehearsal does.

It is reconstructed instead, from the logs themselves. That is the stronger
arrangement anyway: the result artifact both teams must agree on (rule 35) is
then derived from the same disclosed, hash-verified records the opponent audits
(rule 36), rather than from a tally only we can see. If a log is missing, the
result says so by being short, and the discrepancy is visible to both sides.
"""

from __future__ import annotations

from typing import Any

from ..domain.scoring import ScoreTable, SeriesTally
from .result import SubGameOutcome


def _roles(summary: dict[str, Any], mine: str, theirs: str) -> dict[str, str]:
    """Who played what, taken from the log rather than re-derived.

    The parity rule that assigns roles is duplicated on both peers, so a log
    that disagrees with it is evidence of a real problem. Reading the recorded
    role keeps that disagreement visible instead of overwriting it.
    """
    my_role = str(summary.get("role", ""))
    other = "thief" if my_role == "police" else "police"
    return {mine: my_role, theirs: other}


def assemble_series(
    logs: list[dict[str, Any]],
    mine: str,
    theirs: str,
    table: ScoreTable,
    commit_hash: str = "",
) -> tuple[list[SubGameOutcome], dict[str, Any], dict[str, int]]:
    """Turn per-sub-game logs into outcomes, a final result and token totals.

    Input:  every log artifact we wrote for one game against one opponent.
    Output: the three pieces :func:`build_result_artifact` needs.
    Setup:  ``table`` is the agreed score table; ``commit_hash`` is the commit
            that played, recorded per sub-game because the rules allow the code
            to change between sub-games (rule 53).
    """
    tally = SeriesTally(mine, theirs, tie_score=table.tie_score)
    outcomes: list[SubGameOutcome] = []
    tokens = {mine: 0, theirs: 0}

    for log in sorted(logs, key=lambda entry: entry["summary"]["sub_game_number"]):
        summary = log["summary"]
        roles = _roles(summary, mine, theirs)
        outcome = str(summary["result"])
        score = tally.record(roles, outcome, table)
        my_tokens = int(summary.get("tokens_total", 0))
        tokens[mine] += my_tokens
        winner_role = summary.get("winner_role")
        outcomes.append(SubGameOutcome(
            sub_game_number=int(summary["sub_game_number"]),
            roles=roles,
            started_at=str(summary.get("started_at", "")),
            ended_at=str(summary.get("ended_at", "")),
            result=outcome,
            winner_group=next((g for g, r in roles.items() if r == winner_role), None),
            github_commit={mine: commit_hash},
            tokens={mine: my_tokens},
            score=score,
            log_files={mine: log.get("_filename", "")},
            audit=dict(summary.get("audit", {})),
        ))

    return outcomes, tally.finalise(), tokens
