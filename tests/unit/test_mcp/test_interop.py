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


@pytest.fixture
def won(peer_config) -> InteropAdapter:
    """An adapter whose sub-game our cop has just won by capture."""
    from p2pchase.runtime.peer_session import PeerSession

    session = PeerSession(peer_config, "police", "best2934-vs-gal-roy1", sub_game=1, seed=1)
    ready = InteropAdapter(PeerHandlers(peer_config, session))
    ready.turns(session).finished = "capture"
    return ready


def test_a_cop_records_the_capture_it_cannot_see(peer_config):
    """The gap under the ``agree_result`` bug (rules 21, 22, 35).

    ``finished`` was set when we were caught, when we survived, and when they
    claimed survival -- never when *we* captured. The cop is the half that
    cannot see its own win: it claims a cell and the thief answers. Nothing
    wrote that answer down, so a cop that had just won read its own outcome as
    ``""`` and could not agree a result it had earned.
    """
    from p2pchase.runtime.peer_session import PeerSession

    session = PeerSession(peer_config, "police", "best2934-vs-gal-roy1", sub_game=1, seed=1)
    adapter = InteropAdapter(PeerHandlers(peer_config, session))
    loop = adapter.turns(session)
    loop.claimed = (2, 2)

    answer = adapter.confirm_result({"outcome": "CAPTURE", "caught": True, "cell": [2, 2]})
    assert answer["our_outcome"] == "capture"
    assert adapter.our_outcome() == "capture", "and it must survive to agree_result"


def test_taking_a_turn_is_what_records_the_claim(peer_config):
    """The wiring the other tests assume, proved rather than assumed.

    Those set ``claimed`` by hand, which pins the settlement logic and says
    nothing about whether anything ever populates it. If ``take_turn`` did not,
    every concession would be refused as uncorroborated and the cop's outcome
    would stay blank -- the original bug, reintroduced one layer down and still
    passing its own tests.
    """
    from p2pchase.runtime.peer_session import PeerSession

    session = PeerSession(peer_config, "police", "best2934-vs-gal-roy1", sub_game=1, seed=1)
    loop = InteropAdapter(PeerHandlers(peer_config, session)).turns(session)
    assert loop.claimed is None

    turn = loop.take_turn(1)
    assert turn["capture_claim"] is not None, "a cop claims a cell every turn"
    assert loop.claimed == tuple(turn["capture_claim"]), "and we keep what we claimed"


def test_a_conceded_capture_we_never_claimed_is_refused(peer_config):
    """Conceding a capture says *we* won, which is the one direction a lie pays.

    Believed only as far as our own board corroborates it: no claim, no
    settlement. Otherwise any peer could hand us a win by asserting one.
    """
    from p2pchase.runtime.peer_session import PeerSession

    session = PeerSession(peer_config, "police", "best2934-vs-gal-roy1", sub_game=1, seed=1)
    adapter = InteropAdapter(PeerHandlers(peer_config, session))
    adapter.turns(session).claimed = None

    adapter.confirm_result({"outcome": "CAPTURE", "caught": True, "cell": [4, 4]})
    assert adapter.our_outcome() == "", "a win we never claimed is not ours to record"


def test_a_capture_conceded_at_a_cell_we_did_not_claim_is_refused(peer_config):
    """Corroboration is against the *cell*, not merely against having claimed."""
    from p2pchase.runtime.peer_session import PeerSession

    session = PeerSession(peer_config, "police", "best2934-vs-gal-roy1", sub_game=1, seed=1)
    adapter = InteropAdapter(PeerHandlers(peer_config, session))
    adapter.turns(session).claimed = (2, 2)

    adapter.confirm_result({"outcome": "CAPTURE", "caught": True, "cell": [5, 1]})
    assert adapter.our_outcome() == ""


def test_agree_result_names_our_own_outcome_not_just_theirs(won):
    """The bug gal-roy1 reported three times, through two sub-games we won.

    It read only ``sha256``/``expected``, they send ``{"outcome": ...}``, so it
    answered ``ours: "", theirs: ""`` -- our cop had captured their thief twice
    and our own agreement tool could not say so. Rule 35 turns on the two
    reports matching, and a blank matches nothing.
    """
    answer = won.agree_result({"outcome": "CAPTURE"})
    assert answer["our_outcome"] == "capture", "we must compute our own view"
    assert answer["their_outcome"] == "CAPTURE", "and read theirs"
    assert answer["ours"] and answer["theirs"], "both spellings carry the values"
    # "CAPTURE" from them, "capture" from us: the same settlement, and it must
    # not void the match for both teams over a shift key.
    assert answer["agreed"] is True


def test_agree_result_never_agrees_to_an_unnamed_outcome(won):
    """An agreement that names no outcome is not an agreement (rule 35).

    The old code could answer ``agreed`` from fields nobody had populated.
    Filing that is how an honest team files a void.
    """
    assert won.agree_result({"outcome": ""})["agreed"] is False
    assert won.agree_result({})["agreed"] is False


def test_agree_result_refuses_when_we_settled_the_sub_game_differently(won):
    """Two peers reading one sub-game differently is the fault rule 35 exists
    for, and it must surface here rather than in two filed reports."""
    answer = won.agree_result({"outcome": "SURVIVAL"})
    assert answer["agreed"] is False
    assert answer["our_outcome"] == "capture" and answer["their_outcome"] == "SURVIVAL"


def test_agree_result_says_what_its_digest_covers(adapter):
    """Rule 35 voids the match for both teams on contradictory reports, and
    two digests over different objects contradict every time. Cheaper to
    compare the field lists here than to compare two filed reports later."""
    answer = adapter.agree_result({"sha256": "abc"})
    covers = answer["digest_covers"]
    assert "scores" in covers["sub_game"] and "winner" in covers["sub_game"]
    assert "started_at" not in covers["sub_game"], "a private clock must not be in it"
    assert "tokens" not in covers["sub_game"]
