"""Liveness is ``tools/list``, and an unknown tool is not a dead peer.

On 2026-08-08 this peer spent five minutes reporting imreeyal as down while they
were up and pushing sub-game 1 agreements at us. The probe called ``hello``;
they publish no ``hello``; the ``Unknown tool`` surfaced as a
:class:`TransportError`; and the wait loop treats a transport fault as "not here
yet" and retries. Every layer behaved as written and the answer was still wrong,
because two different failures had been collapsed into one.

The tests below are the two halves of that, kept apart deliberately: a peer that
does not answer at all must still be waited for, and a peer that answers without
our names must be played.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from p2pchase.mcp.client import TransportError
from p2pchase.runtime import peer_host


class _Peer:
    """A client double whose surface is the thing under test."""

    def __init__(self, tools: list[str], *, absent_for: int = 0) -> None:
        self.tools = tools
        self.absent_for = absent_for
        self.knocks = 0
        self.greeted = False

    async def list_tools(self) -> list[str]:
        self.knocks += 1
        if self.knocks <= self.absent_for:
            raise TransportError("connection refused")
        return list(self.tools)

    async def hello(self, group_id: str = "") -> dict:
        self.greeted = True
        return {"handshake": {"group_id": "them", "scent_model_sha256": "ab" * 32}}


def _runner(client: _Peer) -> SimpleNamespace:
    return SimpleNamespace(client=client, session=SimpleNamespace(group_id="best2934"))


def _await(client: _Peer, timeout: float = 5.0) -> dict:
    return asyncio.run(peer_host._await_opponent(_runner(client), "http://peer/mcp", timeout))


def test_a_reference_v3_peer_is_up_even_though_it_has_none_of_our_names():
    """The exact surface imreeyal published at 19:00 on 2026-08-08."""
    peer = _Peer(["negotiate", "receive_turn", "submit_audit", "receive_control"])
    assert _await(peer) == {}
    assert peer.knocks == 1, "a live peer must not be knocked on twice"
    assert not peer.greeted, "hello must not be called on a peer that does not publish it"


def test_a_peer_that_publishes_hello_is_still_greeted():
    """The fix must not cost us the early look at their locks."""
    peer = _Peer(["hello", "negotiate"])
    assert _await(peer)["group_id"] == "them"
    assert peer.greeted


def test_a_peer_publishing_nothing_at_all_is_up():
    """An empty surface is strange, but it is an answer. negotiate decides."""
    assert _await(_Peer([])) == {}


def test_a_silent_peer_is_still_waited_for_and_then_given_up_on():
    """The other half: absence really is absence, and the wait stays bounded."""
    peer = _Peer(["negotiate"], absent_for=99)
    with pytest.raises(TransportError, match="never answered tools/list"):
        _await(peer, timeout=0.05)
    assert peer.knocks >= 1


def test_a_peer_that_arrives_late_is_picked_up_rather_than_missed():
    """Two teams never press enter at the same instant."""
    peer = _Peer(["negotiate"], absent_for=2)
    assert _await(peer) == {}
    assert peer.knocks == 3
