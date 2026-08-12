"""A door pinned to one opponent must not seal another opponent's game.

gal-roy1 dialled our standing serve on 2026-08-09 and every record we disclosed
failed their audit. Their diagnosis was careful and its conclusion inverted:
they assumed our hasher was broken. It was not -- we sealed their sub-game in
imreeyal's commitment form, because our autofire driver had restarted the door
with `--game-id best2934-vs-imreeyal` and PeerSession derives the opponent from
the game id exactly once, at construction.

Their bytes proved it. sha256(canonical(payload)|nonce) reproduced what we
disclosed; the merged form reproduced what they computed. Two honest peers,
thirteen unverifiable records, and a counted game blocked.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from p2pchase.domain import kit_seal
from p2pchase.runtime import pairing_guard
from p2pchase.shared.peer_config import PeerConfig

REPO = Path(__file__).resolve().parents[3]


def _config(role: str = "thief") -> PeerConfig:
    read = lambda name: json.loads(  # noqa: E731 -- two reads, one shape
        (REPO / "config" / role / name).read_text(encoding="utf-8"))
    return PeerConfig(role=role, shared=read("game.json"), setup=read("setup.json"))


# ------------------------------------------------------- reading the caller
@pytest.mark.parametrize("payload, expected", [
    ({"group_id": "gal-roy1"}, "gal-roy1"),
    ({"payload": {"group_id": "gal-roy1"}}, "gal-roy1"),          # their nesting
    ({"identity": {"group_id": "imreeyal"}}, "imreeyal"),         # reference-v3
    ({"group_id": "  gal-roy1  "}, "gal-roy1"),
    ({"group_id": ""}, ""),
    ({}, ""),
    (None, ""),
    ("not a dict", ""),
])
def test_caller_group_reads_every_shape(payload, expected):
    assert pairing_guard.caller_group(payload) == expected


# ------------------------------------------------------------ the correction
def _session(opponent: str, game_id: str, records=None):
    config = _config()
    state = SimpleNamespace(board=object())
    return SimpleNamespace(opponent=opponent, game_id=game_id, role="thief",
                           config=config, state=state, records=records or [])


def test_a_caller_who_disagrees_repoints_the_session(monkeypatch):
    """The exact failure: a door opened for imreeyal, dialled by gal-roy1."""
    built = {}
    monkeypatch.setattr(pairing_guard, "build_own_state",
                        lambda *a: built.setdefault("state", SimpleNamespace(board=a[2])))
    session = _session("imreeyal", "best2934-vs-imreeyal")
    assert pairing_guard.adopt(session, {"group_id": "gal-roy1"}) == ""
    assert session.opponent == "gal-roy1"


def test_the_repointed_session_seals_in_the_right_form(monkeypatch):
    """The consequence that actually cost the game."""
    monkeypatch.setattr(pairing_guard, "build_own_state",
                        lambda *a: SimpleNamespace(board=a[2]))
    session = _session("imreeyal", "best2934-vs-imreeyal")
    assert session.config.seal_form(session.opponent) == kit_seal.PIPE
    pairing_guard.adopt(session, {"group_id": "gal-roy1"})
    assert session.config.seal_form(session.opponent) == kit_seal.MERGED


def test_agreement_is_a_no_op():
    session = _session("gal-roy1", "best2934-vs-gal-roy1")
    assert pairing_guard.adopt(session, {"group_id": "gal-roy1"}) == ""
    assert session.opponent == "gal-roy1"


def test_an_anonymous_caller_changes_nothing():
    """Silence is not a claim. Only a named peer outranks the game id."""
    session = _session("imreeyal", "best2934-vs-imreeyal")
    assert pairing_guard.adopt(session, {}) == ""
    assert session.opponent == "imreeyal"


def test_no_session_is_tolerated():
    assert pairing_guard.adopt(None, {"group_id": "gal-roy1"}) == ""


# --------------------------------------------------- too late to switch
def test_a_late_disagreement_refuses_instead_of_switching():
    """Records already sealed under the old terms cannot be re-hashed."""
    session = _session("imreeyal", "best2934-vs-imreeyal", records=[{"payload": {}}])
    refusal = pairing_guard.adopt(session, {"group_id": "gal-roy1"})
    assert refusal
    assert "already sealed" in refusal
    assert session.opponent == "imreeyal", "must not switch mid-chain"


def test_the_late_refusal_names_both_pairings():
    session = _session("imreeyal", "best2934-vs-imreeyal", records=[{}, {}])
    refusal = pairing_guard.adopt(session, {"group_id": "gal-roy1"})
    assert "imreeyal" in refusal and "gal-roy1" in refusal


# ------------------------------------- retiring a sub-game that is over
class _Adapter:
    """The smallest thing shaped like an InteropAdapter for this decision."""

    def __init__(self, session, finished: str = ""):
        self.handlers = SimpleNamespace(session=session)
        self._turns = SimpleNamespace(finished=finished, round=35) if finished != "-" else None
        self.restarted = 0

    def _restart_if_a_new_sub_game(self, payload):
        self.restarted += 1
        self.handlers.session = _session(self.handlers.session.opponent,
                                         self.handlers.session.game_id)


def test_a_finished_sub_game_is_retired_rather_than_defended(monkeypatch):
    """gal-roy1, 2026-08-12: sub-game 4 settled clean, sub-game 5 was refused.

    The records existed and were unextendable -- the sub-game they belonged to
    had ended thirty-five rounds earlier. Refusing to continue a chain nobody
    was continuing is what made our standing door a one-sub-game door.
    """
    monkeypatch.setattr(pairing_guard, "build_own_state",
                        lambda *a: SimpleNamespace(board=a[2]))
    adapter = _Adapter(_session("", "local-rehearsal", records=[{}] * 35),
                       finished="SURVIVAL")
    assert pairing_guard.at_the_door(adapter, {"group_id": "gal-roy1"}) == ""
    assert adapter.restarted == 1
    assert adapter.handlers.session.opponent == "gal-roy1"


def test_a_live_sub_game_still_refuses():
    """The original refusal is untouched: these records can still be extended."""
    adapter = _Adapter(_session("imreeyal", "best2934-vs-imreeyal", records=[{}] * 12))
    refusal = pairing_guard.at_the_door(adapter, {"group_id": "gal-roy1"})
    assert "already sealed" in refusal
    assert adapter.restarted == 0
    assert adapter.handlers.session.opponent == "imreeyal"


def test_the_reset_happens_before_the_pairing_is_judged(monkeypatch):
    """Ordering is the whole defect, so it is asserted directly.

    The three call sites used to run the guard first and the reset second, so
    the guard was handed state the next line would have discarded.
    """
    monkeypatch.setattr(pairing_guard, "build_own_state",
                        lambda *a: SimpleNamespace(board=a[2]))
    seen: list[int] = []
    adapter = _Adapter(_session("", "local-rehearsal", records=[{}] * 35),
                       finished="CAPTURE")
    original = adapter._restart_if_a_new_sub_game

    def spy(payload):
        seen.append(len(adapter.handlers.session.records))
        original(payload)

    adapter._restart_if_a_new_sub_game = spy
    assert pairing_guard.at_the_door(adapter, {"group_id": "gal-roy1"}) == ""
    assert seen == [35], "the reset must see the old records, the guard must not"


def test_a_door_that_has_never_played_needs_no_reset():
    adapter = _Adapter(_session("imreeyal", "best2934-vs-imreeyal"), finished="-")
    assert pairing_guard.at_the_door(adapter, {}) == ""
    assert adapter.restarted == 0


def test_the_same_opponent_returning_for_a_new_sub_game_is_let_through(monkeypatch):
    """imreeyal's case: no pairing change at all, just the next sub-game."""
    monkeypatch.setattr(pairing_guard, "build_own_state",
                        lambda *a: SimpleNamespace(board=a[2]))
    adapter = _Adapter(_session("imreeyal", "best2934-vs-imreeyal", records=[{}] * 35),
                       finished="SURVIVAL")
    assert pairing_guard.at_the_door(adapter, {"group_id": "imreeyal"}) == ""
    assert adapter.restarted == 1
