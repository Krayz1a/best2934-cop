"""The reference-v3 handshake, which is a push in both directions.

This module exists because of a stall we caused and could not see. On
2026-08-09 our cop and imreeyal's thief reached each other, exchanged tool
lists, and then sat still until the deadline expired. Their peer called our
``negotiate`` thirteen times; we answered all thirteen; they recorded **nought
agreements received** and were right to. We had never sent them one.

Two mistakes, and the second is the one worth remembering:

**We never dialled their negotiate at all.**
:func:`~p2pchase.runtime.peer_host._await_opponent` returns an empty handshake
when the peer publishes no ``hello`` -- correct, since ``hello`` is ours and not
theirs -- and :class:`~p2pchase.runtime.reference_driver.ReferenceDriver` then
went straight to waiting for their step-1 turn. Nothing in that path ever
opened its mouth. Their runtime blocks inside ``exchange_agreement`` until our
agreement lands in *their* inbox and will not send a turn before it does, so
both peers waited for a message the other was never going to send.

**Answering their call is not replying to it.** Their client is
``_call_with_retry`` followed by a queue read: it pushes, ignores the response
body entirely, and then waits for our push. Our thirteen well-formed answers
went into a variable they never look at. A request/response habit is invisible
on a fire-and-forget wire, and it fails in the quietest possible way -- both
logs show healthy traffic and neither shows an error.

So the exchange here is symmetric, exactly as
``police_thief.peer.handshake.negotiate`` does it: push ours, wait for theirs,
verify. Ours is the reference's own shape (``terms``, ``nonce``, ``signature``,
``identity``) because that is what their ``verify_peer`` reads.

``identity`` is not optional in practice even though their parser defaults it.
They derive the shared ``game_id`` from ``peer_identity["group_id"]``, falling
back to ``"unknown-group"`` -- so an anonymous agreement does not fail, it
succeeds into two peers labelling the same sub-game differently, which rule 35
voids for both teams at the report diff. It carries our group id, name and
repos, and nothing about any person: identities in this league are groups.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..mcp.client import TransportError
from .watchdog import DeadlineExceededError, TurnDeadline

LOGGER = logging.getLogger(__name__)

#: How long to wait for their agreement once ours is away, and how long to keep
#: re-pushing ours if their server is not accepting yet. Generous on purpose:
#: the two peers are started by two people, and their own client retries for its
#: whole connect timeout before giving up.
AGREEMENT_TIMEOUT_SEC = 60.0
PUSH_RETRY_SEC = 2.0
POLL_INTERVAL_SEC = 0.05


def identity_block(handshake: dict[str, Any]) -> dict[str, Any]:
    """The reference's ``identity`` sub-object, lifted from our flat handshake.

    Group-level facts only. There is nothing personal to leak here -- the league
    identifies teams, never members -- and this is the place to keep it that
    way, because everything in this dict is pushed to an opponent and lands in
    an artifact they may publish.
    """
    return {
        "group_id": handshake.get("group_id", ""),
        "group_name": handshake.get("group_name", ""),
        "repos": dict(handshake.get("repos") or {}),
        # Mirrored from the flat handshake rather than moved. We send both
        # shapes because a reader should not have to know which level a field
        # lives at: ours ride flat on the handshake, anrbj666's reader looks
        # under `identity`, and on 2026-08-15 that cost them two dirty columns
        # in an otherwise clean six -- our data was on their disk the whole
        # time, one level deeper than they looked.
        #
        # Duplication is the cheap side of this trade. A field present twice
        # with the same value costs bytes; a field present once in the wrong
        # place costs a friendly.
        "counted_games_played": handshake.get("counted_games_played", 0),
        "github_commit": handshake.get("github_commit", ""),
    }


def signed_agreement(negotiation: Any, opponent: str,
                     sub_game: int = 0, role: str = "") -> dict[str, Any]:
    """Our handshake in the shape their ``verify_peer`` reads.

    Their check is ``message["terms"] != self.terms`` -- an exact dict
    comparison, not a subset -- then a signature verify over those same terms.
    Our flat handshake already carries all three at the top level, so this adds
    the nested identity beside them rather than reshaping anything.

    ``sub_game_number`` and ``role`` are the kit's **SPEC 7.2 pairing
    declaration**, and they go at the TOP LEVEL for a load-bearing reason: an
    extra key inside ``terms`` would fail that exact dict comparison and get
    every one of our agreements refused. Beside ``terms`` is invisible to their
    check and readable by their gate.

    anrbj666's wire has implemented the 7.2 refusal since 2026-08-14 and it
    never once fired against us, because we declared no number and silence
    cannot mismatch. Declaring it is what lets THEIR side catch a mispaired
    window in one round-trip -- which matters more than our own gate, since the
    reference-v3 turn message carries no sub-game identifier at all and our
    windows are byte-identical, so neither team can attribute a window after
    the fact.
    """
    ours = negotiation.handshake(opponent=opponent).as_dict()
    return dict(ours, identity=identity_block(ours),
                sub_game_number=int(sub_game), role=role)


async def push_agreement(client: Any, agreement: dict[str, Any],
                         timeout: float = AGREEMENT_TIMEOUT_SEC) -> bool:
    """Push ours to their ``negotiate``, retrying while their server refuses.

    Returns whether it ever landed. A failure is reported rather than raised:
    their agreement may still be sitting in our inbox from a call of theirs, in
    which case the sub-game is playable and aborting would forfeit it under
    rule 6 for no reason.
    """
    deadline = TurnDeadline(timeout)
    attempt = 0
    while True:
        attempt += 1
        try:
            answer = await client.call("negotiate", {"message": agreement})
        except TransportError as error:
            LOGGER.info("their negotiate is not accepting yet (attempt %d): %s",
                        attempt, error)
        else:
            if isinstance(answer, dict) and answer.get("ok") is False:
                LOGGER.error("they refused our agreement: %s",
                             answer.get("reason") or answer.get("error"))
            LOGGER.info("our signed agreement pushed to their negotiate (attempt %d)",
                        attempt)
            return True
        try:
            deadline.check("pushing our agreement to their negotiate")
        except DeadlineExceededError:
            LOGGER.error("could not deliver our agreement within %.0fs", timeout)
            return False
        await asyncio.sleep(PUSH_RETRY_SEC)


async def await_agreement(inboxes: Any,
                          timeout: float = AGREEMENT_TIMEOUT_SEC) -> dict[str, Any] | None:
    """Wait for their pushed agreement. ``None`` when none arrives in time.

    ``None`` rather than an exception, for the same reason as above: a peer that
    speaks the rest of the dialect correctly and never negotiates is playable,
    and refusing to play them would be us inventing a requirement to punish
    them with. It is logged loudly instead.
    """
    deadline = TurnDeadline(timeout)
    while not inboxes.agreements:
        try:
            deadline.check("waiting for their signed agreement")
        except DeadlineExceededError:
            LOGGER.warning("no agreement arrived within %.0fs; playing unverified", timeout)
            return None
        await asyncio.sleep(POLL_INTERVAL_SEC)
    return dict(inboxes.agreements.popleft())


def pairing_mismatch(theirs: dict[str, Any], sub_game: int) -> int | None:
    """Their declared sub-game when it is not the one we opened (SPEC 7.2).

    ``None`` when they agree with us **and** when they declare nothing at all.
    Silence cannot refuse: a peer that does not implement 7.2 is not
    mispaired, it is quiet, and inventing a refusal for it would punish them
    for a requirement the rulebook does not make of them. That asymmetry is
    exactly why anrbj666's own gate never fired against us -- we were the
    silent one -- so it is worth being precise about which case is which.

    We report rather than abort. A mispaired window is already dead: their
    side refuses it, so nothing plays either way. Killing our own process on
    top of that risks turning a void into a rule 6 technical loss, which
    charges BOTH teams, and the operator gate on that decision is task #90.
    """
    declared = theirs.get("sub_game_number")
    if not isinstance(declared, int) or not sub_game:
        return None
    return None if declared == sub_game else declared


async def exchange(negotiation: Any, client: Any, inboxes: Any, opponent: str,
                   timeout: float = AGREEMENT_TIMEOUT_SEC,
                   sub_game: int = 0, role: str = "") -> dict[str, Any]:
    """Cross both halves of the handshake and report what the far side said.

    Ours goes first and we do not wait for their call to arrive before sending:
    they may already have pushed and be blocked on us, which is precisely the
    deadlock this module was written for. Whichever peer speaks first unblocks
    the other, so speaking is never the wrong move.

    ``negotiation`` may be ``None``, which means a caller built a driver without
    one and we say so instead of crashing. It is the shape the older tests use.
    """
    if negotiation is None:
        LOGGER.warning("no negotiation service; skipping the agreement exchange")
        return {}
    ours = signed_agreement(negotiation, opponent, sub_game, role)
    delivered = await push_agreement(client, ours, timeout)
    theirs = await await_agreement(inboxes, timeout)
    if theirs is None:
        return {"delivered": delivered, "agreed": False, "group_id": "",
                "reason": "no agreement received"}
    mispaired = pairing_mismatch(theirs, sub_game)
    if mispaired:
        LOGGER.error("PAIRING MISMATCH: we opened sub-game %s and they declared %s. "
                     "This window is not the same sub-game on the two sides and "
                     "anything played in it is unattributable.", sub_game, mispaired)
    verdict = negotiation.compare(theirs)
    LOGGER.info("agreement crossed with %r: agreed=%s%s",
                theirs.get("group_id") or (theirs.get("identity") or {}).get("group_id", ""),
                verdict.agreed,
                "" if verdict.agreed else f" mismatches={verdict.mismatches}")
    return {"delivered": delivered, "agreed": verdict.agreed,
            "group_id": str(theirs.get("group_id")
                            or (theirs.get("identity") or {}).get("group_id", "")),
            "mismatches": list(verdict.mismatches),
            "sub_game_mismatch": mispaired}
