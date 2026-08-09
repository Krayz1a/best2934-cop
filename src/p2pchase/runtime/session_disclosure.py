"""Ending a sub-game: what we disclose, and what we make of theirs.

Split from :class:`~p2pchase.runtime.peer_session.PeerSession` because playing
and proving are different jobs. Everything above this line is a peer deciding
and acting; everything here runs once the board no longer matters, and its only
audience is the audit (rules 18, 19, 36).
"""

from __future__ import annotations

from typing import Any

from ..domain.audit import audit_against_commitments
from ..domain.protocol import Phase
from . import opponent_capture


def final_reveal(session: Any) -> list[dict[str, Any]]:
    """Our complete audit view, nonces included, once the sub-game is over.

    Includes the *pending* step, if the sub-game ended between our commitment
    going out and the step being applied. That happens on nearly every capture:
    the winning claim is answered inside the loser's server, the loser exits,
    and the winner's own step never completes -- so the opponent holds a
    commitment for a step we would otherwise never disclose. In an alternating
    match it happens every time, to whoever moved last.

    Withholding it is not an option, however innocent the cause. An auditor that
    cross-checks live commitments reads the gap as concealment, and it is right
    to: "the last step need not be disclosed" is precisely the loophole worth
    exploiting -- commit, see how the round turned out, then stay silent about
    it. The payload was sealed before the outcome was known, so disclosing it
    costs nothing and proves that.
    """
    session.machine.phase = Phase.FINALISING
    disclosed = list(session.records)
    if session._pending is not None:
        disclosed.append(session._pending[2].audit_view())
    return disclosed


def audit(session: Any, records: list[dict[str, Any]]) -> dict[str, Any]:
    """Verify the opponent's disclosed chain (rules 19, 36).

    Cross-checked against the seals that arrived during play, not merely against
    the ``commit`` each disclosed record carries about itself. Self-consistency
    is free to forge: rewrite the payload, keep the nonce, recompute the hash,
    and the record verifies against its own new seal. What a forger cannot
    change is what we were handed at the time.

    The verdict is kept because the chain can arrive either way round: we ask
    for it, or they push it when they stop first. The second case happens
    exactly when they have gone, so there is nobody left to ask.
    """
    session.opponent_records = list(records)
    session.last_audit = audit_against_commitments(
        records, dict(session.opponent_commitments)).as_dict()
    # Their evidence, not only our verdict. This chain used to exist nowhere but
    # in memory, which is why six failed audits against imreeyal on 2026-08-09
    # could not be diagnosed after the fact. Off unless P2PCHASE_CAPTURE_DIR is
    # set, and it never writes inside either repository.
    opponent_capture.note_audit({"records": records, "verdict": session.last_audit})
    return session.last_audit
