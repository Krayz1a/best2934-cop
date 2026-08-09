"""An empty message must not be the most agreeable message we can receive.

imreeyal reported this on 2026-08-09 from a single liveness probe: we answered
``agreed: true`` to a payload carrying no terms, no signature and no group_id.
Nothing in :meth:`NegotiationService.compare` was individually wrong. Five
separate guards each say "refuse only when BOTH peers declare and the values
differ", each was added because strictness had just turned away a real
opponent, and each is still right. Their conjunction is the bug: declare
nothing and nothing can differ.

The half of this file that matters most is
:func:`test_the_real_imreeyal_greeting_still_clears_the_floor`. A gate is easy
to make strict and the whole history of this function is strictness refusing
opponents we needed under rule 31 -- so the fix is only correct if it still
lets the one real captured greeting we own straight through.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2pchase.services import agreement_floor
from p2pchase.services.negotiation_service import Handshake, NegotiationService
from p2pchase.shared.peer_config import PeerConfig

REPO = Path(__file__).resolve().parents[3]
FIXTURE = REPO / "tests" / "fixtures" / "imreeyal_negotiate_20260808.json"


def _config(role: str = "police") -> PeerConfig:
    read = lambda name: json.loads(  # noqa: E731 -- two reads, one shape
        (REPO / "config" / role / name).read_text(encoding="utf-8"))
    return PeerConfig(role=role, shared=read("game.json"), setup=read("setup.json"))


@pytest.fixture
def service() -> NegotiationService:
    return NegotiationService(_config())


def _hs(**fields: object) -> Handshake:
    """A handshake with every required field blank, so each test states only its point."""
    blank = {"group_id": "", "group_name": "", "code_version": "", "schema_version": "",
             "config_sha256": "", "scent_fingerprint": "", "mcp_url": ""}
    return Handshake(**{**blank, **fields})  # type: ignore[arg-type]


# --------------------------------------------------------------- the floor
def test_an_empty_payload_is_refused(service):
    """The exact message imreeyal probed us with."""
    agreement = service.compare({})
    assert not agreement.agreed


def test_an_empty_payload_is_refused_for_both_stated_reasons(service):
    """Not merely refused -- refused with both faults named, so they can fix once."""
    reasons = " ".join(service.compare({}).as_dict()["mismatches"])
    assert "group_id" in reasons
    assert "nothing to compare" in reasons


def test_naming_yourself_is_not_enough_on_its_own():
    """A greeting that identifies a peer but states no game is still not an agreement."""
    problems = agreement_floor.refusals(_hs(group_id="imreeyal", group_name="imreeyal"))
    assert len(problems) == 1
    assert "nothing to compare" in problems[0]


def test_declaring_terms_is_not_enough_without_a_group_id():
    """Terms we cannot attribute select the wrong pairing's scent model."""
    problems = agreement_floor.refusals(_hs(group_id="", terms={"grid_size": 10}))
    assert len(problems) == 1
    assert "group_id" in problems[0]


@pytest.mark.parametrize("field", agreement_floor.COMPARABLE)
def test_any_single_comparable_field_clears_the_second_requirement(field):
    """None of the five is mandatory. That is the omission rule, kept intact."""
    value = {"grid_size": 10} if field == "terms" else "x"
    problems = agreement_floor.refusals(_hs(group_id="imreeyal", **{field: value}))
    assert problems == []


def test_a_named_peer_with_a_config_digest_clears_the_floor():
    assert agreement_floor.refusals(
        _hs(group_id="gal-roy1", config_sha256="a" * 64)) == []


def test_whitespace_is_not_a_group_id():
    """`" "` is absent wearing a hat; it would select our default terms too."""
    problems = agreement_floor.refusals(_hs(group_id="   ", config_sha256="a" * 64))
    assert len(problems) == 1
    assert "group_id" in problems[0]


def test_the_refusal_says_where_to_put_the_group_id():
    """Both spellings, because the reference-v3 wire nests it under identity."""
    reasons = " ".join(agreement_floor.refusals(_hs()))
    assert "identity.group_id" in reasons


# ------------------------------------------- the check that guards the fix
def test_the_real_imreeyal_greeting_still_clears_the_floor():
    """Captured off the wire 2026-08-08 19:00:06, group_id nested under identity.

    If the floor ever refuses this message, the floor is wrong -- not the
    message. This is the regression that stops a gate written against an empty
    dict from quietly becoming a gate against the league.
    """
    theirs = Handshake.from_dict(json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert agreement_floor.refusals(theirs) == []


def test_the_real_imreeyal_greeting_is_still_agreed(service):
    """End to end, through compare, on the real bytes."""
    agreement = service.compare(json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert agreement.agreed, agreement.as_dict()["mismatches"]


def test_our_own_handshake_clears_the_floor(service):
    """Whatever we send an opponent must satisfy what we demand of them."""
    assert agreement_floor.refusals(service.handshake(opponent="imreeyal")) == []
