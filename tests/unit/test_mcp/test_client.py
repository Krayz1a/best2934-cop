"""The client half of a peer (rules 6, 10).

Two behaviours here decide whether a match survives a flaky opponent, and both
are asserted against stubs rather than a socket.

*A refusal is data, not an exception.* When the opponent answers "no", the
orchestrator has to be able to tell that apart from "the opponent is gone" --
the first is a protocol outcome, the second is an abort.

*The result shape is not ours to control.* FastMCP versions differ in whether a
tool result arrives as structured content, a ``data`` attribute or text blocks.
Losing a league match to a library upgrade would be absurd, so all of them are
accepted and the unrecognised case degrades to a refusal rather than a crash.
"""

from __future__ import annotations

import asyncio
import types

import pytest

from p2pchase import constants
from p2pchase.mcp import contracts
from p2pchase.mcp.client import LoopbackClient, PeerClient, TransportError, _unwrap
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.runtime.peer_session import PeerSession


@pytest.fixture
def loopback(peer_config) -> LoopbackClient:
    session = PeerSession(config=peer_config, role=constants.ROLE_COP, game_id="a-vs-b")
    return LoopbackClient(PeerHandlers(peer_config, session))


# ------------------------------------------------------------ result shapes
@pytest.mark.parametrize("result", [
    types.SimpleNamespace(structured_content={"ok": True}, data=None, content=None),
    types.SimpleNamespace(structured_content=None, data={"ok": True}, content=None),
    types.SimpleNamespace(structured_content=None, data=None, content={"ok": True}),
    {"ok": True},
])
def test_every_transport_result_shape_is_accepted(result):
    assert _unwrap(result) == {"ok": True}


def test_an_unrecognisable_result_becomes_a_refusal_not_a_crash():
    """Rule 6 charges both teams for a stalled sub-game, so we degrade instead."""
    unwrapped = _unwrap("something entirely unexpected")
    assert unwrapped["ok"] is False
    assert "unrecognised tool result" in unwrapped["reason"]


# ------------------------------------------------------------------- setup
def test_a_client_without_an_opponent_url_refuses_to_be_built():
    """Failing here is far better than failing at step one of a league match."""
    with pytest.raises(ValueError, match="opponent_url is empty"):
        PeerClient("")


def test_a_client_carries_the_agreed_response_deadline():
    client = PeerClient("http://127.0.0.1:9902/mcp", timeout=17.0)
    assert client.timeout == 17.0
    assert client.url == "http://127.0.0.1:9902/mcp"


def test_a_transport_failure_names_the_tool_that_failed(monkeypatch):
    """An opaque error mid-match is nearly impossible to diagnose afterwards."""
    class _Broken:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def call_tool(self, tool, payload):
            raise OSError("connection reset")

    client = PeerClient("http://127.0.0.1:9902/mcp")
    monkeypatch.setattr(client, "_connect", lambda: _Broken())

    with pytest.raises(TransportError, match="hello failed: OSError"):
        asyncio.run(client.call(contracts.TOOL_HELLO))


# --------------------------------------------------------------- loopback
def test_the_loopback_client_reaches_every_contract_tool(loopback):
    answer = asyncio.run(loopback.hello())
    assert answer["ok"] is True
    assert set(answer["tools"]) == set(contracts.PUBLISHED_TOOLS)


def test_an_unknown_tool_is_refused_rather_than_raising(loopback):
    """An opponent on a newer protocol must get an answer, not a dropped call."""
    answer = asyncio.run(loopback.call("teleport", {}))
    assert answer["ok"] is False
    assert "unknown tool" in answer["reason"]


def test_a_mismatched_handshake_is_refused_with_its_reasons(loopback, shared_config):
    """Rule 11: byte-identical agreed config, or no match at all."""
    answer = asyncio.run(loopback.negotiate({
        "group_id": "rival999",
        "config_sha256": "0" * 64,
        "scent_fingerprint": "0" * 64,
        "code_version": "1.00",
    }))
    assert answer["ok"] is False
    assert answer["mismatches"]
