"""The caller who names themselves outranks a game id baked in at startup.

Written the hour it cost us a counted game. gal-roy1 dialled our standing
``serve`` on 2026-08-09 and every record we disclosed failed their audit. Their
diagnosis was careful and their conclusion was inverted: they assumed our
hasher had broken. It had not. We sealed their sub-game in *imreeyal's*
commitment form.

The mechanism, and it is entirely ours. ``PeerSession`` derives the opponent
once, in ``__post_init__``, from the ``game_id``. Our autofire driver restarts
the standing door between sub-games with ``--game-id best2934-vs-imreeyal``, so
the door was still asserting that pairing long after the imreeyal series
finished. When gal-roy1 arrived, ``opponent`` read "imreeyal", ``seal_form``
returned the kit's pipe construction, and we sealed a gal-roy1 game in a form
gal-roy1 has never implemented.

Every per-pairing term has this exposure -- ``scent_model``, ``role_convention``
and ``tie_rule`` sit in the same book as ``seal_form`` -- and the failure is the
worst shape available: two honest peers, a clean-looking series, and an audit
that cannot pass. Rule 35 voids that for both teams.

**A game id is an assertion by whoever started the process. A ``group_id`` on
an inbound call is an assertion by the peer it is about.** The second is better
evidence, so it wins -- but only before anything is sealed. After the first
commitment the terms are load-bearing: the records already on the chain were
hashed under the old pairing, and silently switching would produce exactly the
half-and-half chain nobody can audit. So a late disagreement refuses instead,
loudly, while a refusal is still cheap.
"""

from __future__ import annotations

import logging
from typing import Any

from ..domain.own_state import build_own_state
from ..reports.naming import opponent_in_game_id

LOGGER = logging.getLogger(__name__)


def caller_group(payload: dict[str, Any] | None) -> str:
    """The group id a caller claims, from either dialect's shape."""
    if not isinstance(payload, dict):
        return ""
    named = payload
    inner = payload.get("payload")
    if not named.get("group_id") and isinstance(inner, dict):
        named = inner
    identity = named.get("identity")
    if not named.get("group_id") and isinstance(identity, dict):
        named = identity
    return str(named.get("group_id", "") or "").strip()


def at_the_door(adapter: Any, payload: dict[str, Any] | None) -> str:
    """Judge the caller's pairing, after retiring a sub-game that is already over.

    :func:`adopt` refuses when records are already sealed, and that refusal is
    right for records belonging to the chain being played. It is wrong for
    records belonging to a chain that *finished*, and on 2026-08-12 gal-roy1
    hit exactly that: sub-game 4 settled clean at 35 rounds, its records stayed
    in the session, and their sub-game 5 handshake was refused for continuing a
    chain nobody was continuing. Their reading was right -- our standing door
    played one sub-game per process.

    The distinction is what is at stake, not what exists. A finished sub-game's
    records cannot be extended by anything the next caller does; they are
    history, and history is retired here rather than defended. A *live*
    sub-game's records still can be, so that refusal stands untouched.

    Reaching into the adapter is deliberate. The reset and the pairing check
    have to happen in that order at every door, and three call sites each
    remembering to do it in the right order is how the ordering bug happens
    again -- the second time, in this same file's story. One function that
    cannot be called half-way is the fix.

    A caller we are *already* playing changes nothing here and must not, which
    is the correction gal-roy1 filed hours after the first version shipped. The
    outcome of a finished sub-game lives on the turn loop, and retiring the
    sub-game discards it -- so a ``hello`` arriving between the last move and
    ``agree_result`` made us answer with no outcome at all, re-opening the exact
    rule-35 hole we had just closed for them. Retiring is for the peer we are
    changing to, never for the peer we are already talking to.
    """
    session = adapter.handlers.session
    theirs = caller_group(payload)
    if not theirs or session is None or theirs == str(getattr(session, "opponent", "") or ""):
        return ""

    loop = getattr(adapter, "_turns", None)
    if loop is not None and getattr(loop, "finished", ""):
        adapter._restart_if_a_new_sub_game(payload)
    return adopt(adapter.handlers.session, payload)


def adopt(session: Any, payload: dict[str, Any] | None) -> str:
    """Re-point a session at the peer that is actually calling it.

    Returns ``""`` when nothing needed doing, or a refusal reason when the
    disagreement arrived too late to act on safely.
    """
    theirs = caller_group(payload)
    if not theirs or session is None:
        return ""
    ours = str(getattr(session, "opponent", "") or "")
    if theirs == ours:
        return ""

    derived = opponent_in_game_id(getattr(session, "game_id", ""),
                                  session.config.group_id)
    if session.records:
        return (f"this peer opened as {ours!r} (from game_id "
                f"{getattr(session, 'game_id', '')!r}) and you identify as {theirs!r}, "
                f"but {len(session.records)} records are already sealed under the "
                f"first pairing's terms. Restart the sub-game rather than play a "
                f"chain hashed two ways.")

    LOGGER.error("pairing corrected: this door opened as %r (from game_id %r) but the "
                 "caller identifies as %r -- re-deriving the per-pairing terms before "
                 "anything is sealed", ours or derived, getattr(session, "game_id", ""),
                 theirs)
    session.opponent = theirs
    model = session.config.scent_model(theirs)
    # Rebuilt rather than patched: the scent model is baked into the field's
    # physics at construction, so reassigning the name would leave us emitting
    # one model's rings while declaring another's lock. Safe here only because
    # nothing is sealed yet and the board is carried across unchanged.
    session.state = build_own_state(session.config.shared, session.role,
                                    session.state.board, model)
    LOGGER.info("now playing %r on scent_model=%s seal_form=%s role_convention=%s",
                theirs, model, session.config.seal_form(theirs),
                session.config.role_convention(theirs))
    return ""
