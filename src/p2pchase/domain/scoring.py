"""Win conditions and the scoring table (book ch3.5, Appendix F Table 17).

The symmetry is deliberately broken. Capture pays the cop its maximum (20) and
still throws the thief a consolation 5; long survival pays the thief its
maximum (10) and the cop 5. A technical loss -- a crash, a timeout, or proven
cryptographic forgery -- zeroes BOTH sides, so neither team is tempted to win
"on the clock" by stalling the protocol.

Every value here is PERMANENT in Appendix F. Deviation disqualifies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .. import constants

#: The three tie behaviours in the league, as agreed with imreeyal for the
#: pairing constitution. See :meth:`SeriesTally.finalise` for what each does and
#: why the third has to exist even though we do not run it.
SERIES_ADD = "series_add"
SERIES_REPLACE = "series_replace"
PER_SUBGAME = "per_subgame"
TIE_RULES = (SERIES_ADD, SERIES_REPLACE, PER_SUBGAME)

Outcome = Literal["capture", "survival", "technical_loss"]


@dataclass(frozen=True)
class ScoreTable:
    capture_cop: int = constants.CAPTURE_COP
    capture_thief: int = constants.CAPTURE_THIEF
    survival_cop: int = constants.SURVIVAL_COP
    survival_thief: int = constants.SURVIVAL_THIEF
    tie_score: int = constants.TIE_SCORE
    technical_loss: int = constants.TECHNICAL_LOSS

    def award(self, outcome: Outcome) -> dict[str, int]:
        """Points for one finished sub-game, keyed by role."""
        if outcome == constants.OUTCOME_CAPTURE:
            return {constants.ROLE_COP: self.capture_cop, constants.ROLE_THIEF: self.capture_thief}
        if outcome == constants.OUTCOME_SURVIVAL:
            return {constants.ROLE_COP: self.survival_cop, constants.ROLE_THIEF: self.survival_thief}
        if outcome == constants.OUTCOME_TECHNICAL_LOSS:
            return {constants.ROLE_COP: self.technical_loss, constants.ROLE_THIEF: self.technical_loss}
        raise ValueError(f"unknown outcome {outcome!r}")

    def winner_role(self, outcome: Outcome) -> str | None:
        if outcome == constants.OUTCOME_CAPTURE:
            return constants.ROLE_COP
        if outcome == constants.OUTCOME_SURVIVAL:
            return constants.ROLE_THIEF
        return None


def build_score_table(config: dict) -> ScoreTable:
    sc = config.get("scoring", {})
    return ScoreTable(
        capture_cop=int(sc.get("capture_cop", constants.CAPTURE_COP)),
        capture_thief=int(sc.get("capture_thief", constants.CAPTURE_THIEF)),
        survival_cop=int(sc.get("survival_cop", constants.SURVIVAL_COP)),
        survival_thief=int(sc.get("survival_thief", constants.SURVIVAL_THIEF)),
        tie_score=int(sc.get("tie_score", constants.TIE_SCORE)),
        technical_loss=int(sc.get("technical_loss", constants.TECHNICAL_LOSS)),
    )


@dataclass
class SeriesTally:
    """Running totals across the sub-games of one match against one opponent."""

    group_a: str
    group_b: str
    tie_score: int = constants.TIE_SCORE
    #: Which of the three tie behaviours this pairing agreed. Declared rather
    #: than assumed: two conformant teams can legitimately compute different
    #: totals for the same level series and neither is wrong, so the only unsafe
    #: option is leaving it unsaid until a series happens to tie.
    tie_rule: str = SERIES_ADD
    totals: dict[str, int] | None = None
    wins: dict[str, int] | None = None
    ties: int = 0

    def __post_init__(self) -> None:
        if self.totals is None:
            self.totals = {self.group_a: 0, self.group_b: 0}
        if self.wins is None:
            self.wins = {self.group_a: 0, self.group_b: 0}

    def record(self, roles: dict[str, str], outcome: Outcome, table: ScoreTable) -> dict[str, int]:
        """Score one sub-game. ``roles`` maps group_id -> role for this sub-game.

        Under ``per_subgame`` a drawn *row* pays ``tie_score`` to each side here,
        and nothing is applied at the end. Our own engine cannot currently
        produce a drawn row -- capture pays 20/5 and survival 5/10, never equal
        -- which is exactly why this branch is written from the reference's
        published example rather than from anything we can generate. An
        opponent running the reference can hand us one.
        """
        award = table.award(outcome)
        per_group = {group: award[role] for group, role in roles.items()}
        if self.tie_rule == PER_SUBGAME and len(set(per_group.values())) == 1:
            per_group = {group: points + self.tie_score for group, points in per_group.items()}
            self.ties += 1
        for group, points in per_group.items():
            self.totals[group] += points
        winner_role = table.winner_role(outcome)
        if winner_role is not None:
            for group, role in roles.items():
                if role == winner_role:
                    self.wins[group] += 1
        return per_group

    def finalise(self) -> dict:
        """Aggregate result. By default a dead-level series ADDS ``tie_score``.

        The book and the reference implementation contradict each other here,
        and the course grants academic freedom to pick either provided the
        choice is documented and justified (see README, "The tied-series
        scoring choice"). We add; we used to replace.

        **There are three live behaviours, not two.** We proposed the field as
        ``add | replace``; imreeyal took it and added the one we had both
        missed, having gone to the reference's own published example rather than
        adjudicating between two readings of it:

        ============== ============================== =================
        ``tie_rule``   who runs it                    a 25-25 series pays
        ============== ============================== =================
        ``series_add``  this codebase, imreeyal,
                        anrbj666, the league kit       27 / 27
        ``series_replace`` the book's other reading    2 / 2
        ``per_subgame``  the reference implementation  25 / 25, tied *rows* pay 2
        ============== ============================== =================

        ``per_subgame`` is the one worth carrying even though we do not run it.
        The reference has **no series-level adjustment at all** -- it settles a
        drawn sub-game as a tie worth 2 apiece and then plainly sums the rows.
        That agrees with ``series_add`` whenever some sub-game tied, and
        disagrees whenever a series ties without any sub-game tying, which is
        precisely the case the reference's own sparring peer can never generate
        (capture pays 20/5, survival 5/10, never equal). So an unmodified
        reference opponent and this codebase would settle a level series
        differently, having never once disagreed in rehearsal, and rule 35 would
        void it for both of us.

        Book ch9 reads as replacing: "each team receives the tie score", which
        we took to mean the tie score *becomes* the league points for a level
        encounter. The reference sums instead, awarding the tie score per drawn
        sub-game and adding sub-game scores into the total.

        Three reasons we moved to the reference's behaviour:

        * **Rule 35 charges both teams.** A defensible-but-unshared reading
          does not cost only us -- contradictory reports void the match for the
          opponent too, and no reading is worth that.
        * **Every other implementation in this league sums.** Verified against
          copthief-league-protocol SPEC section 6 and its published fixtures.
        * **Replacing inverts the ordering.** Under it a hard-fought 25-25
          series scores 2, less than a single sub-game win pays (20), so a team
          would rank higher for one narrow win than for six drawn ones. That is
          hard to defend as the intent of a rule whose stated purpose is that no
          encounter goes unscored.

        ``raw_score`` still carries the untouched sums, so the tie score applied
        is always visible as the difference rather than baked in irreversibly.
        """
        a, b = self.totals[self.group_a], self.totals[self.group_b]
        series_tie = a == b
        totals = dict(self.totals)
        if series_tie and self.tie_rule == SERIES_ADD:
            totals = {group: value + self.tie_score for group, value in totals.items()}
        elif series_tie and self.tie_rule == SERIES_REPLACE:
            totals = dict.fromkeys(totals, self.tie_score)
        # PER_SUBGAME does nothing here on purpose: its tie score was already
        # paid into the running totals row by row, and the reference applies no
        # series-level adjustment whatsoever.
        return {
            "total_score": totals,
            "raw_score": dict(self.totals),
            "sub_games_won": dict(self.wins),
            "ties": self.ties,
            "winner_group": None if series_tie else (
                self.group_a if a > b else self.group_b),
            "series_tie": series_tie,
            "tie_rule": self.tie_rule,
        }
