"""Every payload we send, put through the real FastMCP tool layer.

The rest of the suite reaches the handlers through
:class:`~p2pchase.mcp.client.LoopbackClient`, which hands the payload dict
straight to the handler. That is the right shape for testing the protocol, and
it is blind to exactly one thing: FastMCP validates a call against the tool's
*signature* and refuses any argument the signature does not name. A key that
:mod:`p2pchase.mcp.contracts` puts on the wire but ``server.py`` forgot to
declare therefore passes every loopback test and fails the first real message
of the first real match -- a technical loss for both teams at move one (rule 6).

So these tests build the actual FastMCP server and call it with the actual
payload builders, asserting the two agree. The transport is FastMCP's in-memory
client rather than a socket: it runs the same tool-call validation, and a test
suite that binds ports is a test suite that fails in CI for reasons nobody
believes. ``tools/rehearsal.py`` covers the socket, in two real processes,
because rules 1 and 2 mean a match must cross one.
"""

from __future__ import annotations

import asyncio

import pytest

from p2pchase import constants
from p2pchase.mcp import contracts
from p2pchase.mcp.client import PeerClient
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.mcp.server import build_server
from p2pchase.runtime.peer_session import PeerSession

GAME_ID = "best2934_vs_transport"


@pytest.fixture
def served(peer_config):
    """A real FastMCP server over a real session, and a client that calls it."""
    session = PeerSession(peer_config, constants.ROLE_COP, GAME_ID, seed=3)
    handlers = PeerHandlers(peer_config, session)
    client = PeerClient(build_server(handlers), timeout=5.0)
    return client, session


def _call(client, tool, payload):
    return asyncio.run(client.call(tool, payload))


def test_a_commit_payload_is_accepted_by_the_published_tool(served):
    """`commit_step` must accept every key `commit_payload` produces."""
    client, _ = served
    payload = contracts.commit_payload(GAME_ID, 1, 1, "best2934", constants.ROLE_COP, "a" * 64)
    assert _call(client, contracts.TOOL_COMMIT, payload)["ok"] is True


def test_a_reveal_payload_including_a_capture_claim_is_accepted(served):
    """The capture claim (rule 21) has to survive the transport, not just the handler."""
    client, _ = served
    commit = contracts.commit_payload(GAME_ID, 1, 1, "best2934", constants.ROLE_THIEF, "b" * 64)
    _call(client, contracts.TOOL_COMMIT, commit)
    reveal = contracts.reveal_payload(
        GAME_ID, 1, 1, "best2934", constants.ROLE_THIEF,
        move="STAY", hint="Still here.", barrier=None,
        intent="truth", capture_claim=[3, 3],
    )
    answer = _call(client, contracts.TOOL_REVEAL, reveal)
    assert answer["ok"] is True
    # A cop asked "are you on (3,3)?"; the answer is the cop's, not ours to fake.
    assert "caught" in answer


def test_a_reveal_with_no_move_at_all_is_accepted(served):
    """I-5, at the layer that actually rejected it.

    A tool's Python signature *is* its published schema, so ``move: str`` with
    no default made the field mandatory on the wire. Every in-process test
    passed -- they call the handler directly -- and two real peers could not
    complete a single step. This is that failure, pinned.
    """
    client, _ = served
    _call(client, contracts.TOOL_COMMIT,
          contracts.commit_payload(GAME_ID, 1, 2, "best2934", constants.ROLE_THIEF, "c" * 64))
    reveal = contracts.reveal_payload(
        GAME_ID, 1, 2, "best2934", constants.ROLE_THIEF,
        hint="Somewhere near the docks.", barrier=None,
    )
    assert "move" not in reveal
    assert _call(client, contracts.TOOL_REVEAL, reveal)["ok"] is True


def test_a_final_reveal_payload_is_accepted(served):
    """`final_reveal` carries the game it belongs to, so the tool must take it."""
    client, _ = served
    payload = contracts.final_reveal_payload(GAME_ID, 1, "best2934", [])
    assert _call(client, contracts.TOOL_FINAL_REVEAL, payload)["ok"] is True


def test_a_scent_query_is_accepted(served):
    client, _ = served
    payload = contracts.scent_query(GAME_ID, 1, 1, [[0, 0], [1, 1]])
    assert _call(client, contracts.TOOL_SCENT, payload)["ok"] is True


def test_every_published_tool_is_reachable(served):
    """The tool list in ``hello`` is a promise; an opponent will hold us to it.

    Asserted as "everything advertised can actually be called", not as equality
    with our native contract. That equality is what we used to assert, and it
    was the bug: the dialect tools were registered and unlisted, so an opponent
    trusting the array would conclude ``propose_config`` did not exist and give
    up before calling it. gal-roy1 found that from the outside. Equality would
    pass again the moment someone advertised a name nothing serves, which is the
    same promise broken from the other end.
    """
    client, session = served
    advertised = set(_call(client, contracts.TOOL_HELLO, {})["tools"])
    server = build_server(PeerHandlers(session.config, session))
    registered = {tool.name for tool in asyncio.run(server.list_tools())}
    assert advertised == registered
    assert {"propose_config", "submit_turn", "confirm_result"} <= advertised


def test_an_undeclared_argument_is_refused_by_the_transport(served):
    """The failure mode this file exists for, pinned so it stays visible.

    A future key added to a payload builder and not to the tool signature comes
    back as a `TransportError`, not as a quietly ignored field.
    """
    from p2pchase.mcp.client import TransportError

    client, _ = served
    payload = contracts.commit_payload(GAME_ID, 1, 1, "best2934", constants.ROLE_COP, "c" * 64)
    payload["a_key_no_tool_declares"] = 1
    with pytest.raises(TransportError):
        _call(client, contracts.TOOL_COMMIT, payload)
