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

from .. import constants
from ..domain.roles import DEFAULT_CONVENTION, cop_group, normalise_role
from ..domain.scoring import SERIES_ADD, ScoreTable, SeriesTally
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


def template_audit(audit: dict) -> dict[str, bool]:
    """The course template's two-field audit row, from our six-field diagnostic.

    Our logs carry `passed`, `verified_steps`, `failed_steps`, `forged_steps`,
    `withheld_steps` and `unsolicited_steps` -- useful when a wire goes wrong,
    and not the shape the grader reads. Appendix F's row is
    ``{"log_verified": ..., "tampered": ...}``.

    imreeyal raised it as the same category as `raw_score` and `tie_rule`,
    which we dropped from the artifact on exactly this argument: the counted
    report goes to the marker, and template-shaped is the only safe shape
    there. Diagnostics stay in the logs, where they belong and where any
    opponent can still audit them; the artifact carries the two fields.

    `tampered` is true when the opponent's disclosed records did not verify --
    forged or withheld steps -- rather than whenever the audit merely failed,
    because a failure with no such step is our own bookkeeping and not an
    accusation against them.
    """
    tampered = bool(audit.get("forged_steps") or audit.get("withheld_steps"))
    return {"log_verified": bool(audit.get("passed", False)), "tampered": tampered}


def canonical_indices(logs: list[dict[str, Any]], mine: str, theirs: str,
                      convention: str) -> list[int]:
    """The series position of each log, derived from the agreed role convention.

    Returns the recorded numbers untouched whenever they are already a complete
    1..N -- which is the normal case and one this must never disturb. It only
    derives when they are not a series at all.

    They were not, against gal-roy1. Our cop and thief repositories each
    numbered their own sub-games from 1, so a six-sub-game series carried the
    indices 1, 1, 2, 2, 3, 3. The totals were right, because sums do not care
    about labels; but `mutual_agreement` scope covers the per-sub-game rows, so
    two teams could agree on 75-35 and still fail a row-by-row join. Agreeing
    on the score while disagreeing about the game is the ambiguity rule 35
    feeds on.

    The position is *derived*, not invented: :func:`~p2pchase.domain.roles
    .cop_group` already says which team cops in which sub-game under the
    pairing's declared convention, so our cop-side logs take the slots where we
    cop and our thief-side logs take the rest, each in recorded order. Both
    peers reach the same answer from the two group ids and the convention
    alone, with nothing to exchange -- the same property that makes the role
    assignment safe in the first place.
    """
    recorded = [int(log.get("summary", {}).get("sub_game_number", 0) or 0)
                for log in logs]
    if sorted(recorded) == list(range(1, len(logs) + 1)):
        return recorded

    total = len(logs)
    cop_slots = [n for n in range(1, total + 1)
                 if cop_group(mine, theirs, n, total, convention) == mine]
    thief_slots = [n for n in range(1, total + 1) if n not in cop_slots]
    slots = {constants.ROLE_COP: iter(cop_slots), constants.ROLE_THIEF: iter(thief_slots)}
    derived = []
    for log in logs:
        role = normalise_role(str(log.get("summary", {}).get("role", "")))
        derived.append(next(slots.get(role, iter(())), 0))
    return derived


def assemble_series(
    logs: list[dict[str, Any]],
    mine: str,
    theirs: str,
    table: ScoreTable,
    commit_hash: str = "",
    tie_rule: str = SERIES_ADD,
    convention: str = DEFAULT_CONVENTION,
) -> tuple[list[SubGameOutcome], dict[str, Any], dict[str, int]]:
    """Turn per-sub-game logs into outcomes, a final result and token totals.

    Input:  every log artifact we wrote for one game against one opponent.
    Output: the three pieces :func:`build_result_artifact` needs.
    Setup:  ``table`` is the agreed score table; ``commit_hash`` is the commit
            that played, recorded per sub-game because the rules allow the code
            to change between sub-games (rule 53); ``tie_rule`` is the pairing's
            declared tied-series rule.

    ``tie_rule`` has to be passed in and cannot default quietly. This is the
    path that builds the result artifact for a **networked** match -- the
    counted one -- and it used to take the ``SeriesTally`` default, so a
    pairing that had declared ``per_subgame`` would still have been settled
    under ``series_add`` here while the local rehearsal honoured the
    declaration. One codebase, two answers, and the disagreement would surface
    at settlement against an opponent who had done nothing wrong.
    """
    tally = SeriesTally(mine, theirs, tie_score=table.tie_score, tie_rule=tie_rule)
    positions = canonical_indices(logs, mine, theirs, convention)
    outcomes: list[SubGameOutcome] = []
    tokens = {mine: 0, theirs: 0}

    # Ordered by the DERIVED position, not the recorded one: sorting by a
    # number we are about to replace would pair each log with another
    # log's slot, and against gal-roy1 the recorded numbers repeat.
    for position, log in sorted(zip(positions, logs, strict=True),
                                key=lambda pair: pair[0]):
        summary = log["summary"]
        roles = _roles(summary, mine, theirs)
        outcome = str(summary["result"])
        score = tally.record(roles, outcome, table)
        my_tokens = int(summary.get("tokens_total", 0))
        tokens[mine] += my_tokens
        winner_role = summary.get("winner_role")
        outcomes.append(SubGameOutcome(
            sub_game_number=position,
            roles=roles,
            started_at=str(summary.get("started_at", "")),
            ended_at=str(summary.get("ended_at", "")),
            result=outcome,
            winner_group=next((g for g, r in roles.items() if r == winner_role), None),
            github_commit={mine: commit_hash},
            tokens={mine: my_tokens},
            score=score,
            log_files={mine: log.get("_filename", "")},
            audit=template_audit(summary.get("audit", {})),
            steps=int(summary.get("steps", 0) or 0),
        ))

    return outcomes, tally.finalise(), tokens
