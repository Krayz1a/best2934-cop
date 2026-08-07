"""How the opponent says a sub-game ended, and how far we believe them.

One rule, given its own module because it is worth more than the two lines it
takes: **the first stated ending wins.**

The rule was written from a real game. gal-roy1 drove our cop through sub-game
1 on 7 August 2026 at 14:48 and sent two ``confirm_result`` calls inside the
same second -- the first conceding ``CAPTURE`` at [5, 1], the second carrying no
outcome at all. The code then read ``outcome or OUTCOME_SURVIVAL``, which turned
an *absence* into a positive claim of survival and overwrote the concession. The
sub-game our cop had just won was recorded as one their thief escaped.

Losing the point is the small half. Our own board still said ``capture``,
because :meth:`TurnLoop.concede` keeps it -- so a single peer held two
contradictory answers to one question, and rule 35 voids the match for *both*
teams when the two reports disagree. gal-roy1 would have lost a game they did
nothing wrong in, over a message they sent to be helpful. Nothing warned. The
only trace was the word ``unstated`` in a log nobody reads mid-game.

Absence still means survival when it comes *first*: a thief that ran the horizon
out has nothing to declare, and reading that silence as survival is what lets an
honest peer stop talking. It was only ever wrong as an overwrite.
"""

from __future__ import annotations

import logging

from .. import constants

LOGGER = logging.getLogger(__name__)


def record_ending(recorded: str, stated: str, sub_game: int) -> str:
    """The ending to keep, given one already held and one just claimed.

    A later ending that *contradicts* the first is refused, and loudly. We
    cannot tell from here whether it is the opponent's bug or an attempt to take
    a concession back, and either way the honest record is what they said when
    they said it -- so this warns and keeps the first rather than choosing.

    Folded to lower case on the way in, which is not tidying. gal-roy1 concedes
    ``"CAPTURE"``; this string becomes the sub-game's outcome in
    :mod:`p2pchase.runtime.peer`, and :meth:`ScoreTable.award` raises
    ``unknown outcome 'CAPTURE'`` on anything that is not exactly one of the
    three lower-case constants. Whether scoring ran at all came down to which
    casing an opponent happened to use.
    """
    claim = str(stated or "").strip().lower()
    if recorded:
        if claim and claim != recorded:
            LOGGER.warning("sub-game %d: opponent now says %s, having already said %s;"
                           " keeping the first", sub_game, claim, recorded)
        return recorded
    LOGGER.info("the opponent has ended sub-game %d: %s", sub_game, claim or "unstated")
    return claim or constants.OUTCOME_SURVIVAL
