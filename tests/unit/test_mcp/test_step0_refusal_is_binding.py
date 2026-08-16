"""A refused step 0 must refuse the whole sub-game, and must refuse the right one.

On 2026-08-16, against gal-roy1, one dial produced both halves of this file's
subject matter.

**The false positive.** They dialled a correct sub-game 4 -- ``first_half``
makes best2934 the thief there, and thief is the door they knocked on -- while
our session counter still read 1, which makes best2934 the cop. ``declare_step0``
judged their role against *our counter* rather than the number they declared,
invented a clash that did not exist, and refused a dial that was right.

**The refusal that did not refuse.** Having refused, we then played all
thirty-five turns anyway, because each later ``submit_turn`` was judged on its
own merits and knew nothing about the rejection. That sealed a complete,
plausible artifact for a sub-game we had already declined -- evidence that looks
exactly like consent.

Either bug alone is bad. Together they cancelled out into a game that was
correct by accident, which is the worst way to be right.
"""

from __future__ import annotations

import pytest

from p2pchase.runtime import declaration_trace


class _Config:
    """Just the two fields the role check reads."""

    num_sub_games = 6

    @staticmethod
    def role_convention(_opponent: str) -> str:
        return "first_half"


class _Session:
    def __init__(self, role: str, sub_game: int) -> None:
        self.role = role
        self.sub_game = sub_game
        self.group_id = "best2934"
        self.opponent = "gal-roy1"
        self.role_clash = ""
        self.declaration_keys: list[list[str]] = []
        self.declared_sub_games: list[int] = []


def _payload(sub_game: int | None, role: str) -> dict:
    body = {"role": role, "group_id": "gal-roy1"}
    if sub_game is not None:
        body["sub_game_number"] = sub_game
    return body


# ------------------------------------------------- judging the right number
def test_the_declared_number_wins_over_our_counter():
    """THE case. Their 4 is correct; our counter says 1; nothing may clash."""
    session = _Session(role="thief", sub_game=1)

    number, clash, theirs = declaration_trace.step0_role_check(
        _payload(4, "police"), session, _Config())

    assert number == 4
    assert clash == ""
    assert theirs == "police"


def test_our_counter_is_the_fallback_when_they_declare_nothing():
    """The only case where ours is the best answer available."""
    session = _Session(role="police", sub_game=2)

    number, clash, _ = declaration_trace.step0_role_check(
        _payload(None, "thief"), session, _Config())

    assert number == 2
    assert clash == ""


def test_a_real_clash_is_still_caught():
    """Guarding against over-correction: sub-game 4 makes us thief, not cop."""
    session = _Session(role="police", sub_game=4)

    _number, clash, _ = declaration_trace.step0_role_check(
        _payload(4, "police"), session, _Config())

    assert clash


def test_a_peer_that_declares_no_role_is_accepted():
    """We cannot check what nobody stated."""
    session = _Session(role="thief", sub_game=4)

    _number, clash, theirs = declaration_trace.step0_role_check(
        _payload(4, ""), session, _Config())

    assert clash == ""
    assert theirs == ""


# --------------------------------------------------- the refusal must bind
def test_an_outstanding_clash_blocks_every_later_call():
    session = _Session(role="thief", sub_game=1)
    session.role_clash = "roles disagree"

    assert declaration_trace.outstanding_clash(session) == "roles disagree"


def test_no_clash_reads_as_empty():
    assert declaration_trace.outstanding_clash(_Session("thief", 1)) == ""


def test_a_session_without_the_field_at_all_is_not_blocked():
    """Defensive: an older session object must not fail closed spuriously."""

    class _Bare:
        pass

    assert declaration_trace.outstanding_clash(_Bare()) == ""


@pytest.mark.parametrize("cleared", ["", None])
def test_a_corrected_step0_clears_the_block(cleared):
    session = _Session(role="thief", sub_game=1)
    session.role_clash = "roles disagree"
    session.role_clash = cleared or ""

    assert declaration_trace.outstanding_clash(session) == ""


# ------------------------------------------------------------- the handler
def test_the_handler_refuses_and_records_the_clash(monkeypatch):
    """The error names the DECLARED sub-game, not ours -- that is the fix."""
    from p2pchase.mcp.handlers import PeerHandlers

    session = _Session(role="police", sub_game=1)
    handlers = object.__new__(PeerHandlers)
    handlers.session = session
    handlers.config = _Config()
    monkeypatch.setattr(PeerHandlers, "_require_session", lambda self: session)

    answer = PeerHandlers.declare_step0(handlers, _payload(4, "thief"))

    assert answer["ok"] is False
    assert answer["sub_game"] == 4
    assert session.role_clash


def test_a_sound_step0_clears_any_previous_clash(monkeypatch):
    from p2pchase.mcp.handlers import PeerHandlers

    session = _Session(role="thief", sub_game=1)
    session.role_clash = "left over from a bad dial"
    session.opponent_records = []
    handlers = object.__new__(PeerHandlers)
    handlers.session = session
    handlers.config = _Config()
    monkeypatch.setattr(PeerHandlers, "_require_session", lambda self: session)

    answer = PeerHandlers.declare_step0(handlers, _payload(4, "police"))

    assert answer["ok"] is True
    assert session.role_clash == ""
