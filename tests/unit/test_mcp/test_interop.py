"""Speaking the opponent's dialect (ADR-019).

gal-roy1's tools take one ``payload`` object; ours name every field. FastMCP
refuses a call whose argument names it does not declare, so two teams agreeing
on every rule in the book still lose at move one (rule 6). These tests cover
the translation, and in particular the two places where a field they need is
somewhere other than where our own surface puts it.
"""

from __future__ import annotations

import pytest

from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.mcp.interop import InteropAdapter

#: Their INTEROP.md section 3 table. ``confirm_result`` is the seventh, added
#: after they hit the case it exists for: a capture that lands inside a
#: piggybacked reply leaves the winner unaware it won until the loser concedes.
THEIR_TOOLS = {"hello", "propose_config", "declare_step0", "submit_turn",
               "confirm_result", "final_audit", "agree_result"}


@pytest.fixture
def adapter(peer_config) -> InteropAdapter:
    return InteropAdapter(PeerHandlers(peer_config))


def test_the_surface_is_exactly_what_they_documented(adapter):
    """CONNECT.md section 2 lists six tools. A seventh is as bad as a missing
    one -- it means we read their document loosely."""
    assert set(adapter.as_map()) == THEIR_TOOLS


def test_hello_puts_identity_where_they_look_for_it(adapter, peer_config):
    """Ours nests these under ``handshake``; theirs reads them at the top.
    Both are sent: a field they ignore is free, a field they cannot find is
    the match."""
    answer = adapter.hello({})
    assert answer["group_id"] == peer_config.group_id
    assert answer["schema_version"]
    # Not pinned to a literal: this is the live number, and pinning it would
    # mean the suite fails the day we legitimately play someone (rule 37).
    assert isinstance(answer["counted_games_played"], int)
    assert answer["handshake"]["group_id"] == peer_config.group_id  # ours, intact


def test_a_refused_config_still_carries_our_digest(adapter):
    """Rule 11. The digest is *most* useful in the message that says no --
    without it they cannot tell whether we disagree or merely failed."""
    answer = adapter.propose_config({"handshake": {
        "group_id": "gal-roy1", "config_sha256": "0" * 64,
        "scent_fingerprint": "0" * 64, "code_version": "1.00"}})
    assert answer["accepted"] is False
    assert len(answer["config_sha256"]) == 64
    assert answer["mismatches"], "a refusal must name what disagreed"


def test_an_agreed_config_is_accepted(adapter, peer_config):
    from p2pchase.services.negotiation_service import NegotiationService

    ours = NegotiationService(peer_config).handshake().as_dict()
    ours["group_id"] = "gal-roy1"  # rule 3: a real opponent has its own code
    answer = adapter.propose_config({"handshake": ours})
    assert answer["accepted"] is True
    assert len(answer["config_sha256"]) == 64


def test_submit_turn_without_a_sub_game_refuses_instead_of_raising(adapter):
    """An exception crosses MCP as an opaque transport failure the opponent
    cannot tell from a crash, and rule 6 charges both teams for the stall."""
    answer = adapter.submit_turn({"step": 7, "commit": "a" * 64})
    assert answer["ack"] is False
    assert "no sub-game" in answer["error"]


def test_agree_result_says_what_its_digest_covers(adapter):
    """Rule 35 voids the match for both teams on contradictory reports, and
    two digests over different objects contradict every time. Cheaper to
    compare the field lists here than to compare two filed reports later."""
    answer = adapter.agree_result({"sha256": "abc"})
    covers = answer["digest_covers"]
    assert "scores" in covers["sub_game"] and "winner" in covers["sub_game"]
    assert "started_at" not in covers["sub_game"], "a private clock must not be in it"
    assert "tokens" not in covers["sub_game"]
