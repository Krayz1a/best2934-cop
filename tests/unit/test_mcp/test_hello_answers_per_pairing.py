"""``hello`` must publish the locks agreed with *the caller*, not our default.

The scent model is a per-pair term: the book's ``multiplicative_book_v1`` with
anrbj666 and gal-roy1, the reference's ``subtractive_chebyshev_v1`` with
imreeyal. ``negotiate`` has always re-derived it from ``theirs.group_id``, but
``hello`` ignored the payload entirely and answered with the default for
everyone -- so our greeting and our verdict disagreed about our own physics for
one of the two pairings, and a peer whose readiness gate reads the greeting saw
the wrong lock before a move.

These run against the *shipped* ``config/`` rather than a fixture, because the
thing under test is that a declared pairing reaches the wire. A synthetic setup
with no ``opponents`` table would pass whatever the code did.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2pchase.domain import scent_models
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.services.negotiation_service import NegotiationService
from p2pchase.shared.peer_config import PeerConfig

REPO = Path(__file__).resolve().parents[3]
BOOK = scent_models.locked_sha256(scent_models.MULTIPLICATIVE)
REFERENCE = scent_models.locked_sha256(scent_models.SUBTRACTIVE)


def _read(role: str, name: str) -> dict:
    return json.loads((REPO / "config" / role / name).read_text(encoding="utf-8"))


@pytest.fixture
def shipped_config() -> PeerConfig:
    return PeerConfig(role="police", shared=_read("police", "game.json"),
                      setup=_read("police", "setup.json"))


@pytest.fixture
def handlers(shipped_config) -> PeerHandlers:
    return PeerHandlers(shipped_config)


def _greeting(handlers: PeerHandlers, group_id=None) -> dict:
    payload = {"group_id": group_id} if group_id is not None else None
    answer = handlers.hello(payload)
    assert answer["ok"], answer
    return answer["handshake"]


def test_the_two_locks_differ_at_all():
    """Guards the test file: equality below would otherwise prove nothing."""
    assert BOOK != REFERENCE


def test_imreeyal_is_told_the_reference_model(handlers):
    assert _greeting(handlers, "imreeyal")["scent_model_sha256"] == REFERENCE


@pytest.mark.parametrize("opponent", ["anrbj666", "gal-roy1"])
def test_the_book_pairings_are_told_the_book_model(handlers, opponent):
    assert _greeting(handlers, opponent)["scent_model_sha256"] == BOOK


def test_an_anonymous_caller_still_gets_our_default(handlers):
    """Silence must not become an error -- every peer greeted us this way until today."""
    assert _greeting(handlers)["scent_model_sha256"] == BOOK
    assert _greeting(handlers, "")["scent_model_sha256"] == BOOK


def test_an_unknown_caller_gets_the_default_rather_than_a_failure(handlers):
    assert _greeting(handlers, "nobody-we-know")["scent_model_sha256"] == BOOK


def test_the_greeting_and_the_verdict_agree_about_our_own_physics(
        handlers, shipped_config):
    """The bug stated as the contradiction it produced.

    ``negotiate`` was right and ``hello`` was wrong. The point of the fix is
    that the two can no longer disagree about what we emit.
    """
    judged = NegotiationService(shipped_config).handshake(
        opponent="imreeyal").scent_model_sha256
    assert _greeting(handlers, "imreeyal")["scent_model_sha256"] == judged == REFERENCE


def test_the_fingerprint_follows_the_model_it_names(handlers):
    """Both locks are keyed on the opponent, or the pair of them lies together."""
    assert (_greeting(handlers, "imreeyal")["scent_fingerprint"]
            != _greeting(handlers, "anrbj666")["scent_fingerprint"])


def test_both_spellings_of_the_caller_name_are_read(handlers):
    """The regression that broke the rehearsal, pinned as a test.

    Our client first sent ``group_id`` at the top level. FastMCP matches
    declared argument names only, so every peer whose ``hello`` declares one
    object refused the call outright and the handshake arrived empty -- the
    exact failure the tool's own docstring had warned about for the empty
    signature, reintroduced from the caller's side. Both shapes are read now.
    """
    flat = _greeting(handlers, "imreeyal")["scent_model_sha256"]
    nested = handlers.hello({"payload": {"group_id": "imreeyal"}})["handshake"]
    assert flat == nested["scent_model_sha256"] == REFERENCE


def test_a_payload_that_is_not_a_mapping_is_survived(handlers):
    """An opponent's dialect is not something we control; it must not raise."""
    assert handlers.hello(None)["ok"]
    assert handlers.hello({"payload": "not-a-dict"})["ok"]


def test_the_terms_and_signature_are_unchanged_by_who_asks(handlers):
    """The fourteen CORE terms are league-wide; only the scent locks are per-pair."""
    reference = _greeting(handlers, "imreeyal")
    book = _greeting(handlers, "anrbj666")
    assert reference["terms"] == book["terms"]
    assert reference["signature"] == book["signature"]
