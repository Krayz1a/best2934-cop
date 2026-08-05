"""Step 0 over the wire: the signed declaration, and the role clash it catches.

Rule 24 wants the hardware declared and signed before play. gal-roy1 asked for
one thing more, and they were right to: the declaration is the last cheap moment
to notice that both peers think they are the cop. Two cops chase nobody, the
sub-game is unplayable, and rule 6 charges *both* teams for the stall -- so the
message that costs a handshake here saves a technical loss there.

What these tests pin is that the check is two-sided. Refusing a clashing peer is
half of it; declaring our own role so *they* can refuse *us* is the other half,
and a peer that only ever checked inbound would leave the opponent blind.
"""

from __future__ import annotations

import asyncio

import pytest

from p2pchase import constants
from p2pchase.mcp import contracts
from p2pchase.runtime import peer_host
from p2pchase.runtime.peer import PeerRunner
from p2pchase.runtime.peer_session import PeerSession

GAME = "test1234-vs-rival999"


class _Recorder:
    """A client that records what was sent and answers however it is told."""

    def __init__(self, answer: dict | None = None, fail: bool = False) -> None:
        self.answer = answer if answer is not None else {"ok": True, "responder_role": "thief"}
        self.fail = fail
        self.sent: list[tuple[str, dict]] = []

    async def call(self, tool: str, payload: dict) -> dict:
        self.sent.append((tool, payload))
        if self.fail:
            raise RuntimeError("no such tool: declare_step0")
        return self.answer


@pytest.fixture
def runner(peer_config):
    session = PeerSession(peer_config, constants.ROLE_COP, GAME, sub_game=4, seed=1)
    return lambda client: PeerRunner(peer_config, session, client, signing_secret="s3cret")


def test_our_role_is_declared_where_the_opponent_can_read_it(runner):
    """Top level as well as sealed inside the signed blob.

    They need it to check the pairing before move one, and making them parse a
    signed structure whose shape we have never agreed with anyone would be a
    poor place to be clever.
    """
    client = _Recorder()
    assert asyncio.run(peer_host.declare_step0(runner(client))) == ""

    tool, sent = client.sent[0]
    assert tool == contracts.TOOL_STEP0
    # One object, under the argument name the tool actually publishes. Sending
    # it flat is not a differently-shaped message, it is a refused one --
    # `test_live_transport` holds that against the real tool layer.
    assert set(sent) == {"payload"}
    payload = sent["payload"]
    assert payload["role"] == constants.ROLE_COP
    assert payload["group_id"] == "test1234"
    assert payload["sub_game_number"] == 4
    assert payload["signature"], "rule 24: the declaration is signed before play"
    assert payload["type"] == "system_spec"


def test_a_refused_declaration_comes_back_as_the_reason(runner):
    client = _Recorder({"ok": False, "reason": "role clash: both peers declared 'police'"})
    assert "both peers declared" in asyncio.run(peer_host.declare_step0(runner(client)))


def test_a_peer_without_the_tool_is_not_treated_as_a_clash(runner):
    """Refusing here would invent a requirement the rulebook does not make.

    Our own declaration is committed as step 0 of our chain either way, which is
    what rule 24 actually asks for.
    """
    assert asyncio.run(peer_host.declare_step0(runner(_Recorder(fail=True)))) == ""


def test_the_signed_declaration_states_the_role_as_well_as_the_hardware(peer_config):
    """Signed rather than merely sent, because the role is the one field an
    opponent might want to argue about after the fact."""
    from p2pchase.infra.sysinfo import build_step0

    payload = build_step0(group_name="best2934", sub_game_number=4, llm_model="template",
                          signing_secret="s3cret", role=constants.ROLE_COP,
                          group_id="best2934")
    assert payload["role"] == constants.ROLE_COP
    assert payload["group_id"] == "best2934"

    from p2pchase.domain.crypto import sign_declaration

    unsigned = {k: v for k, v in payload.items() if k != "signature"}
    assert payload["signature"] == sign_declaration(unsigned, "s3cret")
