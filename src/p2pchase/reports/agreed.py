"""The object two teams hash to prove they recorded the same match (rule 35).

Rule 35 voids a match for BOTH teams when the two filed reports contradict each
other, so this object may contain only facts each peer derives independently --
and both peers must build it under the same *names*. Those are separate
requirements, and we satisfied the first while failing the second: our
canonicaliser reproduced the opponent's worked example byte-for-byte, and our
own summary still differed from theirs in seven places (``groups`` for
``group_ids``, ``winner_group`` for ``winner``, ``"capture"`` for ``"CAPTURE"``
and four more). Identical facts, different digest, void match. The one-sided
test vector could not catch it: it proved our *hasher* against their *object*,
and nobody had tested our object against theirs.

We adopted their spelling, on the grounds that it was already on the wire and
byte-verified -- not on the grounds that we were adapting anyway, which they
rightly refused as a reason.

Two objects, deliberately distinct:

per sub-game
    ``{game_id, group_ids, sub_games}``, exchanged during play. No ``totals``
    key, ever: growing one into it would break the only shape both teams have
    verified against each other.

end of series
    The same, plus ``totals``. Totals are a pure function of the sub-games, so
    hashing them looks redundant -- and is not, because each team files its own
    report. Two sides can agree on all six sub-games and still sum them
    differently, and an aggregation bug is invisible per sub-game and fatal at
    the report.

``scores`` and ``total_score`` both appear because they answer different
questions. ``scores`` is arithmetic and never adjusted; ``total_score`` is the
chapter-9 verdict, which replaces the sums with ``tie_score`` when the series is
level. A mismatch in the first is an arithmetic bug; a mismatch in the second is
a disagreement about chapter 9. Two faults, two fields.
"""

from __future__ import annotations

from typing import Any

from .. import constants

#: Our internal vocabulary follows the book's Hebrew; the wire is uppercase.
WIRE_ROLE = {constants.ROLE_COP: "COP", constants.ROLE_THIEF: "THIEF"}
WIRE_RESULT = {
    constants.OUTCOME_CAPTURE: "CAPTURE",
    constants.OUTCOME_SURVIVAL: "SURVIVAL",
    constants.OUTCOME_TECHNICAL_LOSS: "TECHNICAL_LOSS",
}

#: Per-sub-game keys, in the opponent's spelling. Canonical JSON sorts them, so
#: this tuple documents the field *set*; order is not a risk.
AGREED_SUB_GAME_FIELDS = ("sub_game", "roles", "result", "winner", "tie", "scores")
#: Series keys. ``scores`` and ``total_score`` differ only when chapter 9 fires.
AGREED_TOTALS_FIELDS = ("scores", "sub_games_won", "ties", "winner", "series_tie",
                        "total_score")


def wire_sub_game(outcome: Any) -> dict[str, Any]:
    """One finished sub-game, in the names and casing both teams agreed."""
    as_dict = outcome.as_dict() if hasattr(outcome, "as_dict") else dict(outcome)
    roles = as_dict.get("roles", {})
    result = str(as_dict.get("result", ""))
    return {
        "sub_game": int(as_dict.get("sub_game_number", 0)),
        "roles": {group: WIRE_ROLE.get(role, str(role).upper())
                  for group, role in roles.items()},
        "result": WIRE_RESULT.get(result, result.upper()),
        "winner": as_dict.get("winner_group"),
        "tie": bool(as_dict.get("tie", False)),
        "scores": dict(as_dict.get("score", {})),
    }


def series_totals(group_ids: list[str], sub_games: list[dict[str, Any]],
                  tie_score: int = constants.TIE_SCORE) -> dict[str, Any]:
    """Aggregate the sub-games. Derived only, so a mismatch is a real bug.

    ``ties`` and ``series_tie`` are independent and must not be derived from
    each other: ``ties`` counts sub-games that individually drew, ``series_tie``
    is the chapter-9 condition on the accumulated totals. Under this score table
    a sub-game cannot draw, so a level series has ``ties: 0`` and
    ``series_tie: true`` at the same time.

    A ``TECHNICAL_LOSS`` counts as neither a win nor a tie -- rule 6 zeroes both
    sides, and recording it as a tie would pay out points for it.
    """
    scores = {group: sum(int(game["scores"].get(group, 0)) for game in sub_games)
              for group in group_ids}
    won = {group: sum(1 for game in sub_games if game.get("winner") == group)
           for group in group_ids}
    ties = sum(1 for game in sub_games if game.get("tie"))

    ranked = sorted(scores.values(), reverse=True)
    series_tie = len(ranked) < 2 or ranked[0] == ranked[1]
    winner = None if series_tie else next(
        group for group, total in scores.items() if total == ranked[0])

    return {
        "scores": scores,
        "sub_games_won": won,
        "ties": ties,
        "winner": winner,
        "series_tie": series_tie,
        # A level series ADDS tie_score to each side's sum rather than replacing
        # it. The book and the reference disagree and the course allows either
        # with a documented justification; see README, "The tied-series scoring
        # choice", and SeriesTally.finalise for the reasoning. ``scores`` above
        # keeps the untouched sums, so the adjustment stays visible.
        "total_score": ({group: scores[group] + int(tie_score) for group in group_ids}
                        if series_tie else dict(scores)),
    }


def agreed_summary(game_id: str, group_ids: list[str], sub_games: list[Any],
                   tie_score: int = constants.TIE_SCORE,
                   with_totals: bool = False) -> dict[str, Any]:
    """The hashed object. ``with_totals`` selects the end-of-series shape."""
    wired = [wire_sub_game(game) for game in sub_games]
    summary: dict[str, Any] = {
        "game_id": game_id,
        "group_ids": sorted(group_ids),
        "sub_games": sorted(wired, key=lambda game: game["sub_game"]),
    }
    if with_totals:
        summary["totals"] = series_totals(sorted(group_ids), wired, tie_score)
    return summary
