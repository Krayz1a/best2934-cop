"""Rules 46 and 47 from the thief's side: walls that end the sub-game.

Rule 46 is a barrier dropped on our own cell. Rule 47 is a barrier that takes
our last way out. Both are captures the cop is not obliged to announce, and
both therefore have to be *derived* by the side that can see them -- which for
a hidden-position game is only ever the thief.

--- rule 46 ---------------------------------------------------------------


Until now ``i_am_caught`` was set in exactly one place --
:meth:`PeerSession.answer_capture_claim` -- which fires only when the cop sends
an explicit ``capture_claim`` naming a cell. Our own cop does send one when it
walls a thief. gal-roy1's does not, and nothing in the rulebook obliges it to:
rule 46 says a barrier on the thief's cell *is* a capture, not that the cop must
announce it.

So our thief conceded only when asked, and gal-roy1 walled it six times across
three sub-games and got three SURVIVALs. Their evidence is our own sealed
records, disclosed at ``final_audit`` and verified clean against our commitment
map -- we had committed to those positions before their wall could be known.
About forty-five points, decided by a message we were waiting for and they were
never required to send.

**The conservative reading, deliberately.** A thief that was on the cell when
the wall landed but had already moved off within the round is an I-8 timing
argument, and I-8(a) is still open between us by mutual agreement. This
concedes only the case no reading of the timing can explain away: on the cell
entering the round, and still on it leaving. That is exactly the test gal-roy1
built into their own post-audit checker, and matching their test matters more
than picking the stricter one -- two peers that agree a sub-game is a capture
file one result, and two that disagree void it for both under rule 35.

Being wrong in this direction costs us points. Being wrong in the other
direction files a survival we did not earn, against an opponent holding our
signed record of standing still on the walled cell.

--- rule 47 ---------------------------------------------------------------

The same omission, one cell further out, and it cost us the same way twice.

``OwnState.thief_is_boxed_in`` has existed since the first week and is checked
in :mod:`local_match` and by the live GUI. It was never checked on either
networked wire. So the rule fired in the rehearsal, where nobody is watching,
and never in a match, where the points are.

imreeyal found it on 2026-08-14 from our own disclosed records: in all three
of our thief sub-games we ran to (6,6), they sealed (5,6) and (6,5), and our
thief then sealed thirty consecutive ``STAY`` records against a board it could
see was closed -- and claimed survival at the end of each one. Under rule 47
those are captures. The series was 90-30 to them, not the 47-47 both engines
settled on.

That a boxed thief goes on to *claim survival* is the part that makes this a
rule-35 defect rather than only a lost game: the two reports would have named
different outcomes for a sub-game the opponent won cleanly, and rule 35 voids
such a match for both teams.

We read "no legal move" as no legal *movement*. ``STAY`` is always available,
so the literal reading makes rule 47 unsatisfiable and the rule dead letter;
``Board.has_escape`` has excluded ``STAY`` since it was written. imreeyal reads
it the same way and asked for it in the pairing terms, which is where it
belongs -- a rule both engines derive independently has to be one both engines
spell the same way.
"""

from __future__ import annotations

import logging
from typing import Any

from .. import constants

LOGGER = logging.getLogger(__name__)

Cell = tuple[int, int]


def _cell(value: Any) -> Cell | None:
    """A coordinate pair, or ``None`` for anything that is not one."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return (int(value[0]), int(value[1]))
    except (TypeError, ValueError):
        return None


def entering(session: Any, barrier: Any) -> Cell | None:
    """The wall they just placed, if it landed on us and we are the thief.

    Returns the cell so the caller can re-check it after our move; ``None``
    means there is nothing to watch. The cop is never captured by a barrier,
    so its own walls can never come back at it through this path.
    """
    if session is None or session.role != constants.ROLE_THIEF:
        return None
    wall = _cell(barrier)
    if wall is None or wall != _cell(session.state.position):
        return None
    LOGGER.info("their barrier landed on our cell %s; watching whether we leave", wall)
    return wall


def leaving(session: Any, wall: Cell | None) -> bool:
    """Whether that wall has us: still standing on it after our own move.

    A thief that stepped away is not conceded here. That is the timing case
    I-8(a) has not settled, and conceding it unilaterally would file a capture
    the opponent may not have recorded -- the same rule 35 disagreement from the
    other direction.
    """
    if wall is None or session is None:
        return False
    if wall != _cell(session.state.position):
        LOGGER.info("we moved off the walled cell %s; not conceding on I-8 timing", wall)
        return False
    session.i_am_caught = True
    LOGGER.info("walled in on %s entering and leaving the round: conceding capture "
                "under rule 46", wall)
    return True


def boxed_in(session: Any) -> bool:
    """Rule 47: we are the thief and no movement is left to us.

    Idempotent and cheap, so callers may ask on every round rather than having
    to work out the one moment the last exit closes -- which is not knowable in
    advance, since it can be sealed by their barrier or walked into by our own
    move.

    Sets ``i_am_caught`` for the same reason :func:`leaving` does: that flag is
    what every terminal path already reads, so routing both rules through it
    means the concession, the outcome and the disclosed final record agree
    without any of them having to learn a second way to lose.
    """
    if session is None or session.role != constants.ROLE_THIEF:
        return False
    if not session.state.thief_is_boxed_in():
        return False
    if not session.i_am_caught:
        LOGGER.info("no movement left from %s: conceding capture under rule 47",
                    session.state.position)
    session.i_am_caught = True
    return True
