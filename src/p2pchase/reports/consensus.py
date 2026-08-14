"""The settlement digest in the league's cross-team spelling (rule 35).

We already had one of these. :mod:`p2pchase.reports.agreed` hashes the facts
both peers derive from the same messages -- and that reasoning was right, as it
turns out independently: the copthief-league-protocol kit reached the same
conclusion from the other direction and states it more sharply than we did.

    A whole-body-minus-signature scope is per-side *by construction* (its own
    timestamps and token counts sit inside), so two conformant teams computing
    it can never produce equal hashes.

That is worth keeping in view, because the course reference's
``consensus_signature`` *is* whole-body: ``report_writer.build_report`` signs an
object holding ``תפקיד_מדווח``, ``קבוצה_מדווחת``, ``הצהרות_חתומות_שלי``, the
duration and the token count. Despite its name -- "joint consensus signature" --
two honest peers cannot match it, so it certifies one report against tampering
rather than certifying two reports against each other. Both things are worth
having and they are not the same thing.

So this module exists for the part that has to match *across* teams, in the
spelling the other teams in this league have converged on. Our own
:func:`~p2pchase.reports.agreed.agreed_summary` is unchanged and still published
beside it: gal-roy1 adopted that definition and a peer we already agree with must
not be broken to reach one we have not played yet.

Two differences from ours are cosmetic and one is not:

* **Serialization is spaced**, not compact -- ``json.dumps(..., sort_keys=True,
  ensure_ascii=False)`` with default separators. Nothing justifies it except
  that it is what the lecturer's tooling computes, which is reason enough.
* **Field names**: ``sub_game_number``/``winner_group``/``score``/``aggregate``
  where ours says ``sub_game``/``winner``/``scores``/``totals``.
* A tied series once scored differently here than in our own totals. It no
  longer does -- the course ruled and we moved both. See
  :func:`interop_aggregate`.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .. import constants
from .agreed import wire_sub_game

#: The trimmed per-sub-game row: everything two honest teams must agree on and
#: nothing they may legitimately differ on.
#:
#: Five keys, and ``tie`` is deliberately not the sixth. We carried it until
#: 2026-08-14 on the reasoning that two honest teams must agree a sub-game was
#: tied -- which is true, and still not a reason to hash it. The reference's
#: ``report.emit`` builds this preimage with exactly these five and writes
#: ``tie`` into the *document* row only, so a digest carrying it reproduces
#: nothing anybody plays. Proven against the reference's own published sample
#: artifact rather than argued: see the regression test named for it.
#:
#: The failure mode is the expensive one. A trimmed digest that nobody else
#: computes does not fail loudly at handshake -- it fails at the settlement
#: diff, where two honest reports look contradictory and rule 35 scores both
#: teams zero. Found by anrbj666 against the kit's bundle (league issue #55).
INTEROP_SUB_GAME_FIELDS = ("sub_game_number", "roles", "result", "winner_group",
                           "score")
INTEROP_AGGREGATE_FIELDS = ("total_score", "sub_games_won", "ties", "winner_group",
                            "series_tie")


def interop_canonical(payload: dict[str, Any]) -> str:
    """The league's *second* canonical form: sorted keys, spaced separators.

    Deliberately not :func:`~p2pchase.domain.crypto.canonical_json`, which is
    compact. Both exist on purpose and neither is a mistake: seals and configs
    use the compact form, settlement uses this one. A single "canonical JSON"
    helper used for both would be the bug this module exists to avoid.
    """
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def interop_signature(payload: dict[str, Any]) -> str:
    """SHA-256 over :func:`interop_canonical`."""
    return hashlib.sha256(interop_canonical(payload).encode("utf-8")).hexdigest()


def interop_sub_game(outcome: Any) -> dict[str, Any]:
    """One finished sub-game, trimmed and renamed to the cross-team spelling.

    ``roles`` and ``result`` are taken from the outcome directly rather than
    from :func:`wire_sub_game`, and that is the whole subtlety of this
    function. Our own settlement scope upper-cases them -- ``COP``, ``CAPTURE``
    -- and gal-roy1 adopted that scope, so it stays exactly as it is. The
    league's row is a different row, and it is lower-case: the reference's
    ``report.emit`` writes ``scoring.CAPTURE == "capture"`` and roles
    ``police``/``thief`` straight into the preimage, and the kit's own filed
    pairing artifact reproduces its published digest only with those spellings.

    Our internal constants are already that vocabulary, so passing the raw
    values through *is* the alignment; the upper-casing only ever existed for
    our own scope. Getting the key set right and the values wrong would have
    failed settlement just as completely, and one layer further down where
    nothing would have looked suspicious.

    ``technical_loss`` is ours alone -- the reference's vocabulary is
    ``capture``/``survival``/``timeout``. It passes through unmapped rather
    than guessed at, and is raised with opponents instead: a forfeit is exactly
    when nobody wants to discover a spelling disagreement.
    """
    ours = wire_sub_game(outcome)
    raw = outcome.as_dict() if hasattr(outcome, "as_dict") else dict(outcome)
    return {
        "sub_game_number": ours["sub_game"],
        "roles": dict(raw.get("roles", {})),
        "result": str(raw.get("result", "")),
        "winner_group": ours["winner"],
        "score": ours["scores"],
    }


def interop_aggregate(group_ids: list[str], sub_games: list[dict[str, Any]],
                      tie_score: int = constants.TIE_SCORE) -> dict[str, Any]:
    """Series totals, derived only -- so a mismatch here is a real disagreement.

    A level series ADDS ``tie_score`` to each side's sum rather than replacing
    it -- and since the course ruled on the question, that is now what
    :func:`~p2pchase.reports.agreed.series_totals` does too, so the two agree.

    They did not always. We read chapter 9 as replacing; the reference sums.
    The course confirmed the contradiction is real, granted academic freedom to
    pick either with a written justification, and ours is in the README under
    "The tied-series scoring choice". The deciding argument was not which
    reading is better but that rule 35 charges *both* teams for contradictory
    reports, so a solo-correct reading costs an opponent points as well.
    """
    scores = {group: sum(int(game["score"].get(group, 0)) for game in sub_games)
              for group in group_ids}
    won = {group: sum(1 for game in sub_games if game.get("winner_group") == group)
           for group in group_ids}
    ties = sum(1 for game in sub_games if game.get("tie"))

    ranked = sorted(scores.values(), reverse=True)
    series_tie = len(ranked) < 2 or ranked[0] == ranked[1]
    winner = None if series_tie else next(
        group for group, total in scores.items() if total == ranked[0])

    total = ({group: value + int(tie_score) for group, value in scores.items()}
             if series_tie else dict(scores))
    return {
        "total_score": total,
        "sub_games_won": won,
        "ties": ties,
        "winner_group": winner,
        "series_tie": series_tie,
    }


def interop_summary(game_id: str, sub_games: list[Any], group_ids: list[str],
                    tie_score: int = constants.TIE_SCORE) -> dict[str, Any]:
    """The object both teams hash. ``game_id`` already carries the sorted pair.

    Our own summary also lists ``group_ids`` explicitly. This one does not: the
    league scope omits it because ``game_id`` is built from the sorted pair and
    so already names both teams. Adding a field "for safety" would guarantee the
    mismatch we are trying to avoid -- a preimage is only canonical if nobody
    enriches it.
    """
    rows = sorted((interop_sub_game(game) for game in sub_games),
                  key=lambda row: row["sub_game_number"])
    return {
        "game_id": game_id,
        "aggregate": interop_aggregate(sorted(group_ids), rows, tie_score),
        "sub_games": rows,
    }
