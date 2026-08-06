"""The FastMCP binding (rules 1, 2, 10).

This module is meant to contain no behaviour -- every tool delegates straight to
:class:`~p2pchase.mcp.handlers.PeerHandlers`. So what is tested is the binding
itself: that all eleven protocol tools are actually registered under the names
the opponent will call, and that a tool invoked through the server produces the
same answer as the handler invoked directly. A tool that exists in the contract
but was never wired up would otherwise show up as a mid-match transport error
against a stranger's agent.

No socket is opened. ``serve()`` binds a real port, which a test suite has no
business doing (guidelines §6.1 rule 7).
"""

from __future__ import annotations

import asyncio

import pytest

from p2pchase import constants
from p2pchase.mcp import contracts
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.mcp.server import build_server, serve
from p2pchase.runtime.peer_session import PeerSession

pytest.importorskip("fastmcp", reason="the peer transport is an optional extra")

# The handshake gal-roy1 actually sent on 2026-08-06 at 11:50, trimmed to the
# fields that identify the caller. Kept verbatim rather than invented: the bug
# this pins was in the *shape* of the call, so a tidied-up stand-in would not
# have caught it.
_THEIRS = {"group_id": "gal-roy1", "group_name": "gal-roy1", "schema_version": "1.2",
           "mcp_url": "https://091d-81-199-248-18.ngrok-free.app/mcp"}


@pytest.fixture
def handlers(peer_config) -> PeerHandlers:
    session = PeerSession(config=peer_config, role=constants.ROLE_COP, game_id="a-vs-b")
    return PeerHandlers(peer_config, session)


@pytest.fixture
def server(handlers):
    return build_server(handlers, name="test-peer")


def _tool_names(server) -> set[str]:
    return {tool.name for tool in asyncio.run(server.list_tools())}


def test_every_tool_in_the_contract_is_registered(server):
    """The contract is what an opponent codes against, so it must be complete."""
    assert set(contracts.ALL_TOOLS) <= _tool_names(server)


def test_no_tool_is_exposed_that_nobody_agreed_to(server):
    """Surface area is a liability, so the published set stays closed.

    It is no longer *just* our contract: an opponent whose convention differs
    from ours calls three names of their own (ADR-019), and those are agreed
    too -- in their CONNECT.md rather than in ours. What must not appear is a
    fourth thing neither document names.
    """
    from p2pchase.mcp.interop_server import DISTINCT_TOOLS

    agreed = set(contracts.ALL_TOOLS) | set(DISTINCT_TOOLS)
    assert _tool_names(server) == agreed


def test_the_server_is_named_after_the_peer_running_it(peer_config, handlers):
    """Two peers on one machine must be distinguishable in a log."""
    named = build_server(handlers, name=f"p2pchase-{peer_config.group_id}-police")
    assert peer_config.group_id in named.name


def test_a_tool_answers_exactly_as_its_handler_does(server, handlers):
    """Proof that the binding adds nothing -- which is its entire job."""
    through_server = asyncio.run(server.call_tool("abort", {"reason": "x"}))
    assert through_server.structured_content == handlers.abort({"reason": "x"})


def test_hello_adds_only_the_opponents_aliases_and_removes_nothing(server, handlers):
    """``hello`` is the one tool whose binding is *not* transparent, because two
    teams put identity in different places: ours nests it under ``handshake``,
    theirs reads it at the top level (ADR-019).

    Adding is safe and dropping is not -- a field an opponent ignores costs
    nothing, a field our own client can no longer find costs the match. So this
    pins the direction: a strict superset, never a replacement.
    """
    through_server = asyncio.run(server.call_tool("hello", {})).structured_content
    direct = handlers.hello({})
    assert direct.items() <= through_server.items(), "the binding dropped or altered a field"
    # ``role`` joined the set deliberately: both roles serve the same public URL
    # in turn (rule 41 splits them across repositories), and nothing else on this
    # endpoint says which one is answering.
    assert set(through_server) - set(direct) == {"group_id", "schema_version",
                                                 "role", "counted_games_played"}


@pytest.mark.parametrize("arguments", [
    {"handshake": _THEIRS},
    {"payload": _THEIRS},
    {"payload": {**_THEIRS, "handshake": _THEIRS}},
])
def test_negotiate_accepts_either_spelling_of_its_one_argument(server, handlers,
                                                               arguments):
    """The three shapes gal-roy1 has actually put on the wire (rule 6).

    The third is the one that cost us a sub-game: they nested the fields *and* a
    ``handshake`` key inside ``payload``, trying to satisfy both conventions at
    once. FastMCP matches top-level names only, so it saw a missing
    ``handshake`` and an unexpected ``payload``, and refused before any handler
    ran -- the handler itself had always unwrapped either form.

    Asserted against the handler rather than against named fields, because what
    matters is that the wrapper is invisible: all three spellings must mean the
    same call, whatever ``negotiate`` happens to answer.
    """
    answer = asyncio.run(server.call_tool("negotiate", arguments)).structured_content
    assert answer == handlers.negotiate({"handshake": _THEIRS})


def test_serve_refuses_clearly_when_the_transport_is_absent(peer_config, handlers,
                                                            monkeypatch):
    """A grader on a bare checkout gets a sentence, not an ImportError traceback."""
    import builtins

    from p2pchase.mcp.server import MissingTransportError

    real_import = builtins.__import__

    def _no_fastmcp(name, *args, **kwargs):
        if name == "fastmcp":
            raise ImportError("no fastmcp here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _no_fastmcp)
    with pytest.raises(MissingTransportError, match="uv sync"):
        build_server(handlers)


def test_serve_binds_loopback_and_the_configured_port(peer_config, handlers, monkeypatch):
    """Rule 10 makes publishing the port the tunnel's job, never this process's."""
    captured = {}

    class _Recorder:
        name = "recorder"

        @staticmethod
        def run(**kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("p2pchase.mcp.server.build_server", lambda *a, **kw: _Recorder())
    serve(peer_config, handlers)

    assert captured["transport"] == "http"
    assert captured["host"] == "127.0.0.1"
    assert captured["port"] == peer_config.my_port
    # The 406 diagnostic rides along on every served request; see accept_probe.
    assert len(captured["middleware"]) == 1
