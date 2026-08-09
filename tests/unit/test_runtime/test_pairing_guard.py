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
