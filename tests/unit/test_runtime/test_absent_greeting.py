"""A peer that publishes no ``hello`` must not be refused for saying nothing.

Written from a live failure. At 12:26:16Z on 2026-08-09 our driver refused
imreeyal at step 0 -- ``group_id: absent ... nothing to compare`` -- in the same
second their real agreement arrived inbound on ``negotiate`` and was accepted.
Two log lines, one second apart in the wrong direction:

    handshake REFUSED: group_id: absent ... nothing to compare
    <- opponent called 'negotiate' (call 1)
    handshake agreed with imreeyal (config 7f55c92e5f42ac49)

Nothing was wrong with their greeting. ``_await_opponent`` returns ``{}`` as a
sentinel for "this peer publishes no ``hello``, so we never asked for a
greeting", and ``host_and_play`` handed that sentinel to a gate that had been
hardened an hour earlier to refuse a greeting which *arrived* declaring
nothing. Absent and empty are the same dict and they are not the same claim.

It only ever worked because ``compare`` fail-opened on an empty payload -- the
very defect imreeyal reported. Removing the fail-open was right; it exposed
that one call frame further out we were relying on it. The distinction the fix
turns on is the same one ``agreement_floor`` is built from, applied at the site
that manufactures the silence rather than at the site that reads it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2pchase.services import agreement_floor
from p2pchase.services.negotiation_service import Handshake, NegotiationService
from p2pchase.shared.peer_config import PeerConfig

REPO = Path(__file__).resolve().parents[3]


def _config(role: str = "police") -> PeerConfig:
    read = lambda name: json.loads(  # noqa: E731 -- two reads, one shape
        (REPO / "config" / role / name).read_text(encoding="utf-8"))
    return PeerConfig(role=role, shared=read("game.json"), setup=read("setup.json"))


def _gate(handshake: dict) -> str:
    """`host_and_play`'s rule, isolated: judge a greeting, never a non-greeting."""
    service = NegotiationService(_config())
    if not handshake:
        return ""
    agreement = service.compare(handshake)
    return "" if agreement.agreed else "; ".join(agreement.as_dict()["mismatches"])


def test_an_absent_greeting_is_not_refused():
    """The sentinel from a peer that publishes no hello. This is the regression."""
    assert _gate({}) == ""


def test_a_greeting_that_arrived_declaring_nothing_is_still_refused():
    """The other half. Removing the fail-open must survive fixing the sentinel.

    ``{"handshake": {}}`` is a peer that answered and declared nothing, which is
    what imreeyal's probe sent and what `agreement_floor` exists to refuse.
    """
    refusal = _gate({"group_name": "someone", "mcp_url": "http://example/mcp"})
    assert "group_id" in refusal
    assert "nothing to compare" in refusal


def test_a_real_greeting_still_passes():
    fixture = REPO / "tests" / "fixtures" / "imreeyal_negotiate_20260808.json"
    assert _gate(json.loads(fixture.read_text(encoding="utf-8"))) == ""


@pytest.mark.parametrize("published", [
    ["negotiate", "receive_turn", "submit_audit", "receive_control"],  # imreeyal, live
    ["negotiate"],
])
def test_the_reference_surface_carries_no_hello(published):
    """Why the sentinel exists at all: their four tools do not include one."""
    from p2pchase.mcp import contracts
    assert contracts.TOOL_HELLO not in published


def test_the_floor_itself_is_unchanged_by_this_fix():
    """The fix is at the call site. `agreement_floor` still refuses an empty greeting."""
    blank = {"group_id": "", "group_name": "", "code_version": "", "schema_version": "",
             "config_sha256": "", "scent_fingerprint": "", "mcp_url": ""}
    assert len(agreement_floor.refusals(Handshake(**blank))) == 2  # type: ignore[arg-type]
