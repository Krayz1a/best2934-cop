"""Refusing to play, for the right reasons only (rules 6, 11).

The handshake is the one place where being strict is not automatically safer.
Every mismatch it reports aborts a match, so a comparison that is stricter than
the thing it is comparing turns agreement into a forfeit.

That is not hypothetical here. Our first real opponent published schema 1.2 to
our 1.1. We had already agreed with them on the grid, every Appendix-F
parameter, the scent kernel, the enclosure rule and the canonical JSON encoding
-- and every handshake between us would still have aborted before the first
move, on a version digit whose documented meaning is "optional keys were
added". These tests pin the two halves of the fix: a minor difference plays, a
major difference still refuses.
"""

from __future__ import annotations

import pytest

from p2pchase.services.negotiation_service import NegotiationService


@pytest.fixture
def service(peer_config) -> NegotiationService:
    return NegotiationService(peer_config)


def _theirs(service: NegotiationService, **overrides) -> dict:
    """An opponent who agrees with us about everything except ``overrides``."""
    payload = service.handshake().as_dict()
    payload["group_id"] = "gal-roy1"  # rule 3: a real peer has its own code
    return {**payload, **overrides}


def test_a_minor_version_difference_does_not_abort_the_match(service):
    """The regression. A minor bump only ever adds optional keys, so a peer one
    minor ahead understands every key we send and vice versa."""
    agreement = service.compare(_theirs(service, schema_version="1.9"))
    assert agreement.agreed, agreement.mismatches


def test_a_major_version_difference_still_refuses(service):
    """The half that must not be relaxed with it: a major bump may redefine an
    existing key, and a misread key is worse than a refused handshake."""
    agreement = service.compare(_theirs(service, schema_version="2.0"))
    assert not agreement.agreed
    assert any("schema_version" in m for m in agreement.mismatches)


def test_a_malformed_version_is_refused_and_not_raised(service):
    """This runs inside a tool call an opponent makes. A peer who sends junk
    should be refused a handshake, not be able to raise an exception inside
    ours -- an unhandled error here reads as us going silent (rule 6)."""
    agreement = service.compare(_theirs(service, schema_version="not-a-version"))
    assert not agreement.agreed
    assert any("schema_version" in m for m in agreement.mismatches)


def test_a_config_difference_is_still_blocking(service):
    """Guard against over-correcting: relaxing the version comparison must not
    quietly relax the one that carries the actual game parameters (rule 11)."""
    agreement = service.compare(_theirs(service, config_sha256="0" * 64))
    assert not agreement.agreed
    assert any("config_sha256" in m for m in agreement.mismatches)


def test_our_published_schema_version_matches_our_config(service, peer_config):
    """The bump has to move together. ``config_schema`` validates the file
    against ``constants.SCHEMA_VERSION``, so a half-applied bump makes our own
    config illegal and we refuse ourselves."""
    from p2pchase import constants

    assert service.handshake().schema_version == constants.SCHEMA_VERSION
    assert peer_config.shared["schema_version"] == constants.SCHEMA_VERSION


# --------------------------------------------------------------------------
# The locked-model family (league SPEC section 7). Same lesson as the schema
# digit above, one layer out: a lock that refuses what it has not been told
# refuses the opponents we need.
# --------------------------------------------------------------------------

def test_an_opponent_who_declares_no_scent_lock_is_still_playable(service):
    """Omission is never refusal, in either direction.

    Most of the league declares nothing at all -- an unmodified reference peer
    certainly does not. `scent_fingerprint` is worse: it is *our* construction,
    agreed bilaterally with gal-roy1 and unknown to everyone else, so comparing
    it strictly meant every team that had never heard of it arrived with an
    empty string and was turned away at the handshake. We would have been
    refusing the opponents rule 31 requires us to find, over a field we
    invented, and reading it as their fault.
    """
    agreement = service.compare(_theirs(service, scent_fingerprint="", scent_model_sha256=""))
    assert agreement.agreed, agreement.mismatches


def test_two_declared_and_different_scent_models_do_refuse(service):
    """The case the lock exists for. Two peers running different physics without
    declaring it is the bad outcome, because it *plays* -- and then the audits
    disagree and rule 35 voids the match for both teams."""
    agreement = service.compare(_theirs(service, scent_model_sha256="0" * 64))
    assert not agreement.agreed
    assert any("scent_model_sha256" in m for m in agreement.mismatches)


@pytest.fixture
def two_pairings(peer_config) -> NegotiationService:
    """One peer holding a different scent model against each of two opponents.

    Declared here rather than read from ``config/police/setup.json`` so the test
    pins the *mechanism*. Reading the shipped file would make this pass or fail
    on today's opponent list, which changes every time we recruit someone.
    """
    from p2pchase.domain import scent_models

    peer_config.setup["opponents"] = {
        "gal-roy1": {"scent_model": scent_models.MULTIPLICATIVE},
        "imreeyal": {"scent_model": scent_models.SUBTRACTIVE},
    }
    return NegotiationService(peer_config)


def test_we_declare_the_model_we_agreed_with_the_peer_in_front_of_us(two_pairings):
    """The lock is per-pair, so our own declaration is not a constant.

    gal-roy1 gets the book's model and imreeyal the reference's, from one
    process and one config. A single global would make one of those two
    declarations a false statement about what we run.
    """
    from p2pchase.domain import scent_models

    against_gal = two_pairings.handshake(opponent="gal-roy1").scent_model_sha256
    against_imreeyal = two_pairings.handshake(opponent="imreeyal").scent_model_sha256
    assert against_gal == scent_models.locked_sha256(scent_models.MULTIPLICATIVE)
    assert against_imreeyal == scent_models.locked_sha256(scent_models.SUBTRACTIVE)
    assert against_gal != against_imreeyal


def test_the_scent_fingerprint_describes_the_physics_we_will_actually_run(two_pairings):
    """The declaration has to move with the model.

    Publishing the book's kernel fingerprint while emitting Chebyshev rings
    would be wrong in the direction that matters: it would pass. The opponent
    checks it, sees the value they expected, and the mismatch surfaces later as
    a trail that does not behave.
    """
    assert two_pairings.scent_fingerprint("imreeyal") \
        != two_pairings.scent_fingerprint("gal-roy1")
