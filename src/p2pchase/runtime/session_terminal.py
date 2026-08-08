"""Sealing the last step of a sub-game we have just lost.

A thief that has been caught still owes the cop one more message, and on the
reference-v3 wire it has to be a *real* one. That wire has no response body --
every message is a fire-and-forget push -- so a concession cannot ride back as
the answer to the turn that caught us, the way it does on gal-roy1's dialect.
It has to be a turn of our own, and their validator requires a 64-character
commitment and a non-empty timestamp on every turn it accepts.

Which leaves exactly one honest way to build it: seal a genuine step whose move
is ``STAY``. Reusing an earlier commitment would be equivocation -- two
different payloads announced under one hash -- and inventing a digest that
seals nothing fails the audit at the step it matters most. A sealed STAY costs
nothing (we are already caught, the move changes no outcome) and keeps the
chain contiguous, so the opponent's audit still reproduces every commitment
including this one.

The alternative is to send nothing, and that is the failure the kit rates worst
in its own tracker: the cop cannot see the board, so a thief that simply stops
leaves the cop waiting out its budget and settling as a *timeout* a sub-game it
actually won. The two sides then report one game two different ways, which is
the shape rule 35 voids for both teams.

Kept out of :class:`~p2pchase.runtime.peer_session.PeerSession` for the same
reason as :mod:`session_disclosure`: it is not how a peer plays, it is how a
peer stops. That the session module is also at its size limit is a happy
coincidence rather than the reason.
"""

from __future__ import annotations

from typing import Any

from .. import constants
from ..domain.brains import Decision
from ..domain.crypto import commit
from ..domain.protocol import StepIntent
from ..mcp.turn_message import TurnMessage

#: The one move that asserts nothing. Named here because this module's whole
#: argument is that the terminal step must be *this* move and not another.
STAY = "STAY"

#: What the terminal step says out loud. Fixed rather than composed, because
#: the talk engine may reach an LLM and a concession must not be able to fail,
#: stall or lie -- rule 22 makes a false word here a forfeit, and this is the
#: one sentence in a sub-game with nothing left to gain by deceiving.
CONCESSION_HINT = "Caught. Standing still and closing out the sub-game."

#: The same step when it is not a concession -- the thief still owes an answer
#: to the cop's final claim, or has survived and must say so. Distinct wording
#: so a log tells the two endings apart at a glance.
CLOSING_HINT = "Sub-game closed. Standing still."


def seal_stay(session: Any, step: int, hint: str = CONCESSION_HINT) -> str:
    """Seal a truthful ``STAY`` at ``step`` and return its commitment.

    Bypasses the brain deliberately. Asking a strategy what to do after the
    sub-game is decided invites it to answer with a move, and a move would
    claim the game is still running.

    Leaves the record pending exactly as :meth:`PeerSession.prepare_step` does,
    so the caller finishes it with the usual ``apply_own_step`` /
    ``end_of_turn`` pair and :func:`session_disclosure.final_reveal` discloses
    it whether or not that happened.
    """
    session.step = step
    decision = Decision(move=STAY, barrier=None,
                        intent=constants.INTENT_TRUTH, rationale="conceding the sub-game")
    intent = StepIntent(
        step=step, role=session.role, sub_game_number=session.sub_game,
        move=decision.move, hint=hint, intent=decision.intent, barrier=None,
        position=session.state.settled_position(decision.move, None),
    )
    record = commit(intent.payload())
    session._pending = (decision, hint, record)
    return record.commit


def build_terminal(session: Any, loop: Any, sender: str, step: int,
                   response: dict[str, Any] | None) -> dict[str, Any]:
    """The whole terminal message, sealed and ready to push (reference-v3).

    Owed on three conditions, and it took reading the reference's own sparring
    peer to get them all: we were caught, we still owe an answer to a claim, or
    we survived. Only the first is obvious, and shipping only the first is a
    live bug -- the cop claims a cell on *every* round including the last, so a
    thief that answers only when caught leaves the final claim unanswered, and
    a cop cannot see the board well enough to tell "you missed" from "I have
    gone".

    The sentence is sealed and disclosed as one value. Sealing the concession
    while sending a different hint would make our own final record fail the
    audit it exists to survive.

    Lives here rather than on the driver because it is the same argument the
    module docstring makes: this is how a peer stops, not how it plays.
    """
    caught = session.i_am_caught
    hint = CONCESSION_HINT if caught else CLOSING_HINT
    commitment = seal_stay(session, step, hint)
    state = session.state
    survived = state.survival_reached() and not state.is_cop
    turn = TurnMessage(
        step=step, sender=sender, commit=commitment, hint=hint,
        # The real lagged field, never ``{}``: to a strict physics checker an
        # empty grid reads as a trail that vanished for one step rather than as
        # a peer that has finished speaking.
        scent_grid=loop.trail(),
        claim_response=response,
        win_claim={"type": "survival", "steps": int(state.step)} if survived else None,
    ).as_dict()
    session.apply_own_step()
    session.end_of_turn()
    return turn
