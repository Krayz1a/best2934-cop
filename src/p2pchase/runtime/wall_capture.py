"""Rule 46 from the thief's side: noticing a barrier dropped on our own cell.

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
