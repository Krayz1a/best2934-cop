"""Answering a proposed config (rules 11, 12).

The bug pinned here was diagnosed by the opponent from our own reply, not by
any test of ours: they sent ``{"config": <their game.json>}`` and we answered
with three mismatches whose ``theirs`` values were all the empty string. We
were parsing a config proposal as a fingerprint handshake, finding no
fingerprints in it, and refusing a legal config against our own real values.

The check exists to prove two canonicalisations agree -- they send an object,
we hash *that object* -- not to prove their defaults equal ours. Read the other
way it can only pass against a peer whose file is byte-identical to ours, which
no independently written group's will be.
"""

from __future__ import annotations

import copy

import pytest

from p2pchase.domain.crypto import canonical_json, sha256_hex
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.mcp.interop import InteropAdapter


@pytest.fixture
def adapter(peer_config) -> InteropAdapter:
    return InteropAdapter(PeerHandlers(peer_config))


def test_a_proposed_config_is_hashed_and_accepted(adapter, peer_config):
    """The regression. Their payload shape, and the digest they asked for."""
    answer = adapter.propose_config({"config": peer_config.shared})
    assert answer["accepted"] is True
    assert answer["config_sha256"] == sha256_hex(canonical_json(peer_config.shared))
    assert answer["illegal_terms"] == []


def test_both_digests_cover_the_same_shape(adapter, peer_config):
    """Otherwise the two numbers differ for a reason that has nothing to do
    with either config. Our ``hello`` publishes a digest over a *subset* of
    sections; a proposing peer hashes its whole file. Reporting one of each
    would read as a disagreement about the game when it is a disagreement
    about scope, so the subset digest is sent under its own name."""
    answer = adapter.propose_config({"config": peer_config.shared})
    assert answer["config_sha256"] == answer["our_config_sha256"]
    assert answer["our_agreed_terms_sha256"] == peer_config.config_sha256()
    assert answer["our_agreed_terms_sha256"] != answer["our_config_sha256"]


def test_the_digest_is_of_their_object_not_of_ours(adapter, peer_config):
    """The heart of it: we must hash what they sent. Answering with our own
    digest would agree with ourselves and prove nothing about their encoding."""
    theirs = copy.deepcopy(peer_config.shared)
    theirs["world"] = {**theirs["world"], "map_area": "Tel Aviv"}
    answer = adapter.propose_config({"config": theirs})
    assert answer["config_sha256"] == sha256_hex(canonical_json(theirs))
    assert answer["config_sha256"] != answer["our_config_sha256"]


def test_a_negotiable_difference_is_reported_but_accepted(adapter, peer_config):
    """``map_area`` is freely negotiable. Adopting their term is what
    negotiating *is*; refusing it would make rule 11 unsatisfiable."""
    theirs = copy.deepcopy(peer_config.shared)
    theirs["world"] = {**theirs["world"], "map_area": "Tel Aviv"}
    answer = adapter.propose_config({"config": theirs})
    assert answer["accepted"] is True
    assert any("map_area" in term for term in answer["differing_terms"])


def test_an_illegal_permanent_term_is_still_refused(adapter, peer_config):
    """The line that must not move. Appendix F PERMANENT terms may not change,
    and agreeing to one would be a disqualification we consented to (rule 12)."""
    theirs = copy.deepcopy(peer_config.shared)
    theirs["board_and_agents"] = {**theirs["board_and_agents"], "grid_size": 5}
    answer = adapter.propose_config({"config": theirs})
    assert answer["accepted"] is False
    assert any("grid_size" in term for term in answer["illegal_terms"])
    # Still carries the digest: a refusal without one cannot be diagnosed.
    assert len(answer["config_sha256"]) == 64


def test_the_older_handshake_shape_still_works(adapter, peer_config):
    """Our own client sends fingerprints. Fixing their shape must not break the
    one that already worked."""
    from p2pchase.services.negotiation_service import NegotiationService

    ours = NegotiationService(peer_config).handshake().as_dict()
    ours["group_id"] = "gal-roy1"
    answer = adapter.propose_config({"handshake": ours})
    assert answer["accepted"] is True


def test_commentary_keys_are_not_treated_as_terms(adapter, peer_config):
    """``_schema`` and ``_remark`` are prose for humans. Diffing them would
    report a disagreement about a sentence as a disagreement about the game."""
    theirs = copy.deepcopy(peer_config.shared)
    theirs["_schema"] = "their wording of the same thing"
    answer = adapter.propose_config({"config": theirs})
    assert answer["differing_terms"] == []
    assert answer["accepted"] is True


#: gal-roy1's config, as they describe it: no ``pheromone_kernel`` key, so our
#: ``build_kernel`` falls back to the book table for the 5x5 / 0.9 case.
THEIR_PHEROMONES = {"pheromone_center_intensity": 0.9, "pheromone_decay": 0.1,
                    "pheromone_grid_size": 5}
AGREED_SCENT_FINGERPRINT = "e6a37eba68fc217534d08d0aba710515801fa218c24cd491d4e41fd96b3e8b2d"


def test_the_model_lock_is_derived_from_the_proposed_config(adapter, peer_config):
    """Page 47, moved to where the question is first well-posed.

    The fingerprint must come from the object this call agrees, not from either
    side's file: we do not play under their file or ours. Asserted against the
    literal gal-roy1 published, from the config shape they actually send.
    """
    theirs = copy.deepcopy(peer_config.shared)
    theirs["pheromones"] = dict(THEIR_PHEROMONES)

    answer = adapter.propose_config({"config": theirs})
    assert answer["agreed_scent_fingerprint"] == AGREED_SCENT_FINGERPRINT


def test_the_model_travels_with_its_own_digest(adapter, peer_config):
    """So a mismatch is diffed rather than guessed -- and so that the object
    published IS the object hashed. Two teams comparing a digest against a
    *description* of what it covers is how this cost a week."""
    theirs = copy.deepcopy(peer_config.shared)
    theirs["pheromones"] = dict(THEIR_PHEROMONES)

    answer = adapter.propose_config({"config": theirs})
    model = answer["agreed_scent_model"]
    assert sha256_hex(canonical_json(model)) == answer["agreed_scent_fingerprint"]


def test_a_kernel_disagreement_moves_the_lock(adapter, peer_config):
    """The failure it exists to catch: same parameters, different table.

    ``gaussian`` reproduces the book figure to within 0.01 everywhere except the
    diagonal. Every pheromone *field* matches, so ``differing_terms`` is quiet
    about the physics and only the fingerprint separates them.
    """
    theirs = copy.deepcopy(peer_config.shared)
    theirs["pheromones"] = {**THEIR_PHEROMONES, "pheromone_kernel": "gaussian"}

    answer = adapter.propose_config({"config": theirs})
    assert answer["agreed_scent_fingerprint"] != AGREED_SCENT_FINGERPRINT
    assert answer["accepted"] is True, "a different kernel is legal, just not silent"
