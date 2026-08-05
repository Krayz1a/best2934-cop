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
