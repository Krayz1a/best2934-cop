"""The opponent's six tool names, on a real FastMCP server (rule 6).

:mod:`tests.unit.test_mcp.test_interop` tests the adapter by calling its
methods. That cannot catch the failure that actually costs a match: an adapter
that is perfectly correct and never *bound*, so an opponent's ``hello`` reaches
a server that has never heard of it. We shipped exactly that -- the adapter sat
finished and unregistered while we discussed the protocol with the other team.

So this asks the server what it publishes, rather than asking our own code what
it thinks it published. The tool list is read from FastMCP itself for the same
reason: ``hello`` reporting its own tool list is a self-report, and a
self-report is the thing under test.
"""

from __future__ import annotations

import asyncio

import pytest

from p2pchase import constants
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.mcp.interop_server import DISTINCT_TOOLS, SHARED_NAMES
from p2pchase.mcp.server import build_server
from p2pchase.runtime.peer_session import PeerSession

GAME_ID = "best2934_vs_interop"

#: Every name gal-roy1's CONNECT.md section 2 says they will call.
THEIR_TOOLS = frozenset(DISTINCT_TOOLS) | frozenset(SHARED_NAMES)


@pytest.fixture
def server(peer_config):
    session = PeerSession(peer_config, constants.ROLE_COP, GAME_ID, seed=3)
    return build_server(PeerHandlers(peer_config, session))


def _tools(server) -> dict:
    """What the transport actually advertises, keyed by name."""
    from fastmcp import Client

    async def go():
        async with Client(server) as client:
            return {tool.name: tool for tool in await client.list_tools()}

    return asyncio.run(go())


def _call(server, tool, arguments):
    from fastmcp import Client

    async def go():
        async with Client(server) as client:
            return (await client.call_tool(tool, arguments)).data

    return asyncio.run(go())


def test_the_server_publishes_every_tool_the_opponent_will_call(server):
    """The regression: the adapter existed and nothing bound it."""
    missing = THEIR_TOOLS - set(_tools(server))
    assert not missing, f"an opponent calling these gets 'unknown tool': {sorted(missing)}"


def test_hello_accepts_their_one_object_convention(server):
    """Their client sends ``{"payload": {...}}``. A signature naming no argument
    at all does not ignore that -- it refuses the call."""
    answer = _call(server, "hello", {"payload": {"group_id": "gal-roy1"}})
    assert answer["group_id"]
    assert isinstance(answer["counted_games_played"], int)


def test_hello_still_accepts_our_own_no_argument_call(server):
    """Widening the signature must not break the caller that already worked."""
    assert _call(server, "hello", {})["handshake"]["group_id"]


def test_declare_step0_accepts_either_spelling_of_its_argument(server):
    """We named it ``declaration`` and they named it ``payload``. The name *is*
    the published schema, so both have to be declared or one team is refused."""
    body = {"group_id": "gal-roy1", "role": "COP", "code_version": "1.0"}
    assert _call(server, "declare_step0", {"declaration": body})["ok"] is not None
    assert _call(server, "declare_step0", {"payload": body})["ok"] is not None


def test_agree_result_answers_their_payload_form(server):
    """Rule 35. Their form carries ``{outcome, agreement}``; ours carries the
    digests flat. Both must reach the same comparison."""
    answer = _call(server, "agree_result", {"payload": {"sha256": "abc"}})
    assert "digest_covers" in answer


def test_submit_turn_answers_a_nil_opening_with_a_real_turn(server):
    """The opening handover, over the published tool rather than the adapter.

    A nil turn carries no commitment and must not advance a round counter, but
    it does pass the token -- so the answer to one is our first real move.
    """
    answer = _call(server, "submit_turn", {"payload": {
        "step": 0, "sender": "THIEF", "commit": None, "hint": None,
        "scent_grid": {}, "nil": True}})

    assert answer["ack"] is True
    reply = answer["reply_turn"]
    assert reply["step"] == 1
    assert len(reply["commit"]) == 64
    assert "move" not in reply and "state" not in reply  # I-5


def test_confirm_result_is_published_and_records_a_concession(server):
    """They asked for this one: without it the winner of a piggybacked capture
    never learns it won, and rule 35 voids the match for both teams."""
    answer = _call(server, "confirm_result", {"payload": {
        "outcome": "capture", "caught": True, "cell": [2, 2]}})
    assert answer["ack"] is True
    assert answer["recorded"] is True
