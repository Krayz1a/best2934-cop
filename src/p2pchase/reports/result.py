"""The final result report -- the binding artifact e-mailed to the lecturer.

This is the file that decides what the match was worth, and two book rules make
it unforgiving. Rule 34: it must be sent as an attached JSON file, never as free
text; a plaintext report is rejected and scores zero. Rule 35: BOTH teams must
send their own copy and the two must agree -- a missing or contradicting report
voids the match for both sides.

``mutual_agreement.sha256`` is how agreement is proved rather than asserted.
Each team computes the digest over the same agreed summary; two matching digests
show the teams recorded the same match, and a mismatch exposes a contradiction
that no amount of arguing afterwards can talk away.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .. import constants
from ..domain.crypto import mutual_agreement_hash
from .agreed import agreed_summary as build_agreed_summary
from .naming import TIMEZONE, links_block


@dataclass
class SubGameOutcome:
    """One finished sub-game, as it appears in the result report.

    Input:  the facts both teams agreed on for a single sub-game.
    Output: :meth:`as_dict`, a row in the result artifact.
    Setup:  ``tie`` is explicit rather than inferred from equal scores, because
            a dead-level series pays both sides ``tie_score`` and that is a
            different outcome from two independent draws.
    """

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


def agreed_summary(game_id: str, groups: list[str], sub_games: list[SubGameOutcome],
                   final_result: dict[str, Any] | None = None) -> dict[str, Any]:
    """The part of the result the two teams must agree on, and only that (rule 35).

    The shape and the spelling live in :mod:`p2pchase.reports.agreed`, which is
    where the reasoning is. This wrapper keeps the report's own call site
    unchanged and drops ``final_result``: totals are recomputed from the
    sub-games rather than taken from our scoring engine, so that both peers
    derive the hashed number from the same six facts instead of each trusting
    its own aggregator. Our engine's figures are still reported -- they are
    just no longer the thing that is hashed.
    """
    return build_agreed_summary(game_id, groups, sub_games, with_totals=True)


def build_result_artifact(
    game_id: str,
    game_uid: str,
    groups: list[str],
    sub_games: list[SubGameOutcome],
    final_result: dict[str, Any],
    tokens_total_series: dict[str, int],
    confirmed: bool = False,
    repositories: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Assemble the report both teams send independently.

    ``repositories`` carries *four* links -- both teams' cop and thief
    repositories (rule 49). The lecturer reads the result JSON, not the e-mail
    body, so the links have to be inside the artifact; and carrying the
    opponent's pair as well means either team's report alone is enough to find
    all four, which is what makes a missing counter-report survivable.
    """
    summary = agreed_summary(game_id, groups, sub_games, final_result)
    return {
        "_schema": (
            "Summary and final result for the WHOLE game (all sub-games) "
            "between two teams: per-sub-game scores and the aggregate outcome "
            "used to build the league standings. Both teams must agree on this "
            "result and each sends its own copy to the lecturer (book ch9)."
        ),
        "schema_version": constants.SCHEMA_VERSION,
        "report_type": "final_game_result",
        "game_id": game_id,
        "game_uid": game_uid,
        "links": links_block(game_id),
        "repositories": repositories or {},
        "timezone": TIMEZONE,
        "groups": sorted(groups),
        "num_sub_games": len(sub_games),
        "sub_games": [sub_game.as_dict() for sub_game in sub_games],
        "final_result": {**final_result, "tokens_total_series": tokens_total_series},
        "mutual_agreement": {
            "sha256": mutual_agreement_hash(summary),
            "confirmed": confirmed,
        },
    }
