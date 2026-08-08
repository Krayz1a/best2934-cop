"""A real reference-v3 greeting must be accepted, not manufactured into a refusal.

Every assertion here runs against ``tests/fixtures/imreeyal_negotiate_20260808.json``
-- imreeyal's actual sub-game 1 agreement, captured off the wire at 19:00:06 on
2026-08-08. It reached our log intact and never reached our code, because
FastMCP refused it over the *name* of the argument carrying it.

Two separate defects had to be fixed for this message to be playable, and only
the first was visible at T:

1. ``negotiate`` declared ``handshake`` and ``payload``; the reference sends
   ``message``.
2. ``Handshake.from_dict`` read a top-level ``group_id``; the reference nests it
   under ``identity``. ``compare`` re-derives our own per-pair terms from
   ``theirs.group_id``, so an unread group id selects our *default* scent model
   -- the book's, where the reference's was agreed with this opponent. We would
   have refused them for a physics disagreement invented by our own parser.

The second is why this file uses the real fixture rather than a hand-written
greeting: a synthetic message would have been written with a top-level
``group_id``, and would have passed against the broken parser.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2pchase.domain import core_terms, roles, scent_models
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.services.negotiation_service import Handshake, NegotiationService
from p2pchase.shared.peer_config import PeerConfig

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "tests" / "fixtures" / "imreeyal_negotiate_20260808.json"
REFERENCE = scent_models.locked_sha256(scent_models.SUBTRACTIVE)
BOOK = scent_models.locked_sha256(scent_models.MULTIPLICATIVE)


def _config(role: str = "police") -> PeerConfig:
    read = lambda name: json.loads(  # noqa: E731 -- two reads, one shape
        (REPO / "config" / role / name).read_text(encoding="utf-8"))
    return PeerConfig(role=role, shared=read("game.json"), setup=read("setup.json"))


@pytest.fixture
def greeting() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def service() -> NegotiationService:
    return NegotiationService(_config())


def test_their_signature_verifies_under_our_own_implementation(greeting):
    """The single pipe, proven against a real peer's bytes rather than a vector."""
    assert core_terms.signature_verifies(
        greeting["terms"], greeting["nonce"], greeting["signature"])


def test_the_group_id_is_read_out_of_the_identity_block(greeting):
    """The defect that would have refused them after the argument name was fixed."""
    assert Handshake.from_dict(greeting).group_id == "imreeyal"


def test_the_identity_block_does_not_override_a_flat_group_id():
    """Flat wins where both are present -- we must not rewrite a peer's own label."""
    both = {"group_id": "flat", "identity": {"group_id": "nested"}}
    assert Handshake.from_dict(both).group_id == "flat"


def test_a_greeting_with_no_identity_block_still_parses():
    """The league's flat shape is the one gal-roy1 and our own peers send."""
    assert Handshake.from_dict({"group_id": "gal-roy1"}).group_id == "gal-roy1"


def test_an_identity_that_is_not_a_mapping_is_survived():
    assert Handshake.from_dict({"identity": "nonsense"}).group_id == ""


def test_reading_their_group_selects_the_reference_model_not_the_book(greeting, service):
    """The mechanism behind the refusal, isolated.

    Unread group id -> default terms -> the book's model. Both peers would then
    declare a scent lock and the two would differ, which is exactly the
    condition ``lock_refuses`` exists to refuse.
    """
    theirs = Handshake.from_dict(greeting)
    assert service.handshake(opponent=theirs.group_id).scent_model_sha256 == REFERENCE
    assert service.handshake(opponent="").scent_model_sha256 == BOOK


def test_their_real_greeting_is_agreed(greeting, service):
    agreement = service.compare(greeting)
    assert agreement.agreed, agreement.mismatches


def test_their_fourteen_terms_are_identical_to_ours(greeting, service):
    ours = service.handshake(opponent="imreeyal").terms
    assert core_terms.term_differences(ours, greeting["terms"]) == []
    assert len(greeting["terms"]) == 14


def test_the_scent_locks_agree_rather_than_merely_not_refusing(greeting, service):
    """Not the omission rule: BOTH sides declare here, and they must match."""
    assert greeting["scent_model_sha256"] == REFERENCE
    assert service.handshake(opponent="imreeyal").scent_model_sha256 == REFERENCE


def test_the_unregistered_info_mode_lock_is_not_a_refusal(greeting, service):
    """They declare a family we do not register; omission is never a mismatch."""
    assert greeting["info_mode_sha256"]
    assert service.compare(greeting).agreed


def test_the_handler_accepts_the_greeting_end_to_end(greeting):
    answer = PeerHandlers(_config()).negotiate({"handshake": greeting})
    assert answer["ok"], answer.get("mismatches")


def test_their_declared_role_is_the_mirror_of_ours_on_sub_game_one(greeting):
    """A role clash is the one stop condition worth catching before a move."""
    config = _config()
    ours = roles.role_for("best2934", "imreeyal", greeting["sub_game_number"],
                          config.num_sub_games, config.role_convention("imreeyal"))
    assert greeting["role"] == "thief"
    assert ours == "police"
