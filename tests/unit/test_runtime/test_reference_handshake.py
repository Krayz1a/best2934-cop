"""The reference-v3 agreement exchange, and the deadlock it exists to prevent.

Every test here is a consequence of one live failure. On 2026-08-09 our cop and
imreeyal's thief connected, agreed on nothing, and both waited: their runtime
blocks until our signed agreement reaches their inbox, and we had no code path
that ever sent one. Both logs looked healthy. The sub-game was recorded as a
technical loss with the wire in perfect working order.

The first test is the regression and the rest are the shape of the fix. The
important one is :func:`test_the_driver_pushes_negotiate_before_the_first_turn`
-- not because pushing is subtle, but because *not* pushing was invisible.
"""

from __future__ import annotations

import asyncio

import pytest

from p2pchase import constants
from p2pchase.mcp.client import TransportError
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.mcp.reference_v3_server import Inboxes
from p2pchase.runtime import reference_handshake
from p2pchase.runtime.peer_session import PeerSession
from p2pchase.runtime.reference_driver import ReferenceDriver
from p2pchase.services.negotiation_service import NegotiationService


def _run(coro):
    return asyncio.run(coro)


class _Peer:
    """A far side that behaves like the reference: push in, nothing useful back.

    ``police_thief.infra.mcp_client._call`` discards the response body, so this
    returns ``{"ok": True}`` and records the message. A test that asserted on
    our return value would be testing a channel no reference peer reads.
    """

    def __init__(self, *, refuse: bool = False, dead_calls: int = 0) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.refuse = refuse
        self.dead_calls = dead_calls

    async def call(self, tool: str, payload: dict | None = None) -> dict:
        if self.dead_calls > 0:
            self.dead_calls -= 1
            raise TransportError(f"{tool} failed: peer not up")
        self.calls.append((tool, dict(payload or {})))
        if self.refuse:
            return {"ok": False, "reason": "configuration mismatch"}
        return {"ok": True}

    @property
    def agreements(self) -> list[dict]:
        return [body.get("message", {}) for name, body in self.calls
                if name == "negotiate"]


def _service(peer_config) -> NegotiationService:
    return NegotiationService(peer_config)


# --------------------------------------------------------------- the regression
def test_the_driver_pushes_negotiate_before_the_first_turn(peer_config):
    """The bug of 2026-08-09, asserted directly.

    We are the cop here, so the thief opens and our first action is to wait.
    Before this fix that wait was the *whole* of our behaviour and their peer
    was waiting on us at the same instant.
    """
    session = PeerSession(config=peer_config, role=constants.ROLE_COP, game_id="a-vs-b")
    peer, near = _Peer(), Inboxes()
    driver = ReferenceDriver(peer_config, session, peer, near, _service(peer_config))
    _run(driver.handshake())
    assert [name for name, _ in peer.calls] == ["negotiate"]


def test_a_driver_with_no_negotiation_service_says_so_rather_than_pretending(peer_config):
    """The old two-argument construction still runs, and admits what it skipped."""
    session = PeerSession(config=peer_config, role=constants.ROLE_COP, game_id="a-vs-b")
    peer = _Peer()
    driver = ReferenceDriver(peer_config, session, peer, Inboxes())
    assert _run(driver.handshake()) == {}
    assert peer.calls == []


# ------------------------------------------------------------------ the message
def test_our_agreement_carries_the_three_fields_their_verifier_reads(peer_config):
    """``verify_peer`` reads ``terms``, ``nonce`` and ``signature``, top level."""
    agreement = reference_handshake.signed_agreement(_service(peer_config), "imreeyal")
    assert agreement["terms"]
    assert agreement["nonce"]
    assert agreement["signature"]


def test_our_agreement_carries_an_identity_with_our_group_id(peer_config):
    """They derive the shared game_id from it, defaulting to 'unknown-group'.

    An absent identity does not fail their handshake -- it succeeds into two
    peers labelling the same sub-game differently, which rule 35 voids at the
    report diff. Silence is the dangerous answer here, not an error.
    """
    agreement = reference_handshake.signed_agreement(_service(peer_config), "imreeyal")
    assert agreement["identity"]["group_id"] == peer_config.group_id


def test_the_identity_block_carries_nothing_personal(peer_config):
    """Group-level facts only. This dict is pushed to an opponent."""
    identity = reference_handshake.identity_block(
        {"group_id": "best2934", "group_name": "Best", "repos": {"cop": "url"}})
    assert set(identity) == {"group_id", "group_name", "repos"}


def test_it_is_sent_under_message_because_that_is_their_argument_name(peer_config):
    """``negotiate`` takes ``message``; ``submit_audit`` takes ``payload``."""
    peer = _Peer()
    _run(reference_handshake.push_agreement(peer, {"terms": {}}))
    assert peer.calls[0][0] == "negotiate"
    assert "message" in peer.calls[0][1]


# ------------------------------------------------------------------- delivering
def test_a_peer_that_is_not_up_yet_is_retried(peer_config, monkeypatch):
    """Two people press enter at two different times; theirs retries too."""
    monkeypatch.setattr(reference_handshake, "PUSH_RETRY_SEC", 0.0)
    peer = _Peer(dead_calls=3)
    assert _run(reference_handshake.push_agreement(peer, {"terms": {}}, timeout=5.0))
    assert len(peer.calls) == 1


def test_a_peer_that_never_accepts_reports_failure_rather_than_raising(peer_config,
                                                                       monkeypatch):
    """Rule 6: aborting a playable sub-game is worse than playing it unverified."""
    monkeypatch.setattr(reference_handshake, "PUSH_RETRY_SEC", 0.0)
    peer = _Peer(dead_calls=10_000)
    assert _run(reference_handshake.push_agreement(peer, {"terms": {}}, timeout=0.0)) is False


def test_a_refusal_is_logged_and_still_counts_as_delivered(peer_config, caplog):
    """They received it and said no. That is an answer, not a lost message."""
    peer = _Peer(refuse=True)
    with caplog.at_level("ERROR"):
        assert _run(reference_handshake.push_agreement(peer, {"terms": {}}))
    assert "refused our agreement" in caplog.text


# ---------------------------------------------------------------------- waiting
def test_their_pushed_agreement_is_taken_off_the_queue(peer_config):
    inboxes = Inboxes()
    inboxes.agreements.append({"group_id": "imreeyal"})
    assert _run(reference_handshake.await_agreement(inboxes))["group_id"] == "imreeyal"
    assert not inboxes.agreements


def test_no_agreement_in_time_returns_none_rather_than_aborting(peer_config, caplog):
    """A peer that speaks the rest of the dialect and never negotiates is playable."""
    with caplog.at_level("WARNING"):
        assert _run(reference_handshake.await_agreement(Inboxes(), timeout=0.0)) is None
    assert "playing unverified" in caplog.text


# --------------------------------------------------------------- both halves
def test_the_exchange_crosses_both_directions(peer_config):
    """Ours goes out, theirs comes off the queue, and the verdict is reported."""
    inboxes = Inboxes()
    service = _service(peer_config)
    inboxes.agreements.append(service.handshake(opponent="imreeyal").as_dict())
    peer = _Peer()
    verdict = _run(reference_handshake.exchange(service, peer, inboxes, "imreeyal"))
    assert verdict["delivered"]
    assert peer.agreements[0]["identity"]["group_id"] == peer_config.group_id


def test_we_push_first_and_do_not_wait_to_be_spoken_to(peer_config, monkeypatch):
    """The deadlock: both peers waiting for the other to open.

    Whichever side speaks first unblocks the other, so speaking is never the
    wrong move -- and here nothing is in our inbox at all when we send.
    """
    monkeypatch.setattr(reference_handshake, "PUSH_RETRY_SEC", 0.0)
    peer, inboxes = _Peer(), Inboxes()
    _run(reference_handshake.exchange(_service(peer_config), peer, inboxes,
                                      "imreeyal", timeout=0.0))
    assert peer.agreements, "we must push even with an empty inbox"


def test_a_mismatch_is_reported_and_not_swallowed(peer_config):
    """Their terms disagreeing with ours is a thing to tell them, not to hang on."""
    inboxes = Inboxes()
    inboxes.agreements.append({"group_id": "imreeyal", "terms": {"max_moves": 1},
                               "nonce": "abc", "signature": "wrong"})
    verdict = _run(reference_handshake.exchange(_service(peer_config), _Peer(),
                                                inboxes, "imreeyal"))
    assert verdict["agreed"] is False
    assert verdict["mismatches"]


# ------------------------------------------------------------- the inbound half
def test_our_negotiate_handler_queues_what_it_was_sent(peer_config):
    """Answering their call is not replying to it: their client drops the body.

    The queue is the only channel a reference-v3 peer's handshake can reach us
    on, and until 2026-08-09 nothing filled it.
    """
    handlers = PeerHandlers(peer_config)
    handlers.negotiate({"handshake": {"group_id": "imreeyal", "terms": {}}})
    assert handlers.reference_inboxes.agreements[0]["group_id"] == "imreeyal"


def test_a_refused_agreement_is_still_queued(peer_config):
    """The driver needs to know it arrived; a mismatch is a report, not a wait."""
    handlers = PeerHandlers(peer_config)
    handlers.negotiate({"handshake": {"group_id": "imreeyal", "terms": {"max_moves": 1},
                                      "nonce": "n", "signature": "bad"}})
    assert len(handlers.reference_inboxes.agreements) == 1


def test_clearing_between_sub_games_keeps_agreements(peer_config):
    """A stale turn corrupts a board; a dropped agreement hangs a handshake.

    Their peer sends the same fourteen terms every sub-game, so consuming an
    early one is harmless. Losing one that arrived a moment before we cleared
    is not: they will not send a turn until ours crosses.
    """
    inboxes = Inboxes()
    inboxes.turns.append({"step": 1})
    inboxes.agreements.append({"group_id": "imreeyal"})
    inboxes.clear()
    assert not inboxes.turns
    assert inboxes.agreements


@pytest.mark.parametrize("empty", [{}, None])
def test_an_empty_negotiate_payload_queues_nothing(peer_config, empty):
    """A probe with no body must not look like an agreement to the driver.

    Only the two shapes that can actually arrive. A non-dict cannot: every
    spelling of the argument is declared ``dict[str, Any] | None``, so FastMCP
    refuses it before the handler runs, and anything that somehow got past that
    meets :mod:`p2pchase.mcp.tool_guard` rather than the wire. Parametrising a
    ``str`` in here would be testing the framework's job and asserting a
    guarantee this function does not make.
    """
    handlers = PeerHandlers(peer_config)
    handlers.negotiate({"handshake": empty} if empty is not None else {})
    assert not handlers.reference_inboxes.agreements
