"""The handshake blocker with imreeyal, in both directions.

Before this, our greeting carried no ``terms``/``nonce``/``signature`` and our
``compare`` refused any peer whose ``config_sha256`` differed from ours -- which
includes every peer that does not send one. imreeyal's gate refuses a greeting
with no CORE terms. So we refused them and they refused us, on every sub-game,
and the friendly could not start in either direction.

Both halves are pinned here, because both were ours to fix.
"""

from __future__ import annotations

from p2pchase.domain import core_terms
from p2pchase.services.negotiation_service import Handshake, NegotiationService


def _theirs(config, group_id="imreeyal", **overrides):
    """A kit-CORE greeting from a peer that is NOT built like us.

    No ``config_sha256`` and no ``scent_*`` locks -- the shape imreeyal actually
    sends. Their terms agree with ours by value, which is the case that has to
    be playable.
    """
    payload = {"group_id": group_id, "group_name": group_id,
               "schema_version": config.shared["schema_version"],
               **core_terms.signed_agreement(config.shared)}
    payload.update(overrides)
    return payload


def test_our_handshake_now_carries_the_core_agreement(peer_config):
    """The missing half of the greeting, and it must verify against itself."""
    published = NegotiationService(peer_config).handshake().as_dict()

    assert set(published["terms"]) == set(core_terms.CORE_KEYS)
    assert published["nonce"] and published["signature"]
    assert core_terms.signature_verifies(
        published["terms"], published["nonce"], published["signature"])


def test_the_existing_fields_are_still_published(peer_config):
    """Additive. Teams that gate on what we used to send must not break.

    gal-roy1 compares ``config_sha256`` and anrbj666 reads the scent locks; a
    fix for imreeyal that dropped either would trade one blocked pairing for
    two.
    """
    published = NegotiationService(peer_config).handshake().as_dict()
    for key in ("group_id", "code_version", "schema_version", "config_sha256",
                "scent_fingerprint", "scent_model_sha256", "mcp_url", "repos"):
        assert key in published, f"{key} disappeared from the greeting"


def test_a_peer_that_sends_no_config_sha256_is_played_not_refused(peer_config):
    """The blocker, from our side. This is the assertion imreeyal is waiting on.

    Their greeting carries no ``config_sha256`` at all. We used to compare ours
    against the empty string, call it a mismatch and refuse -- having argued to
    them, about their gate, that a digest over a differently-shaped object
    carries no information when it differs.
    """
    agreement = NegotiationService(peer_config).compare(_theirs(peer_config))

    assert agreement.agreed, agreement.mismatches
    assert not any("config_sha256" in m for m in agreement.mismatches)


def test_two_peers_that_both_declare_a_differing_config_sha256_still_refuse(peer_config):
    """Omission is not refusal; disagreement between declarers still is."""
    service = NegotiationService(peer_config)
    agreement = service.compare(_theirs(peer_config, config_sha256="deadbeef" * 8))

    assert not agreement.agreed
    assert any("config_sha256" in m for m in agreement.mismatches)


def test_the_fourteen_values_are_compared_where_the_digest_could_not(peer_config):
    """What replaces the digest as the actual gate.

    A peer whose terms differ is refused on the *term*, by name and by value,
    rather than on a hash that says only "something, somewhere".
    """
    theirs = _theirs(peer_config)
    theirs["terms"] = {**theirs["terms"], "barriers_max": 15, "max_steps": 40}
    theirs["signature"] = core_terms.sign_terms(theirs["terms"], theirs["nonce"])

    agreement = NegotiationService(peer_config).compare(theirs)

    assert not agreement.agreed
    assert any("terms.barriers_max" in m and "15" in m for m in agreement.mismatches)
    assert any("terms.max_steps" in m and "40" in m for m in agreement.mismatches)


def test_a_peer_whose_signature_does_not_verify_is_refused(peer_config):
    """An internally inconsistent agreement is not an agreement.

    Reported as a signature failure and not as fourteen value mismatches: the
    two mean different things and send the humans to different files. The most
    likely cause is the ``|`` ambiguity, so the message names the construction.
    """
    theirs = _theirs(peer_config)
    theirs["terms"] = {**theirs["terms"], "barriers_max": 15}  # signature not recomputed

    agreement = NegotiationService(peer_config).compare(theirs)

    assert not agreement.agreed
    assert any("signature does not verify" in m for m in agreement.mismatches)
    assert any("single pipe" in m for m in agreement.mismatches)


def test_a_peer_that_sends_no_terms_at_all_is_still_played(peer_config):
    """The omission rule again, now for the field we just added.

    gal-roy1 sends no CORE terms. Having just been refused for exactly this by
    a gate that assumed everyone speaks its dialect, we are not going to build
    the same gate pointing the other way.
    """
    agreement = NegotiationService(peer_config).compare(
        {"group_id": "gal-roy1", "schema_version": peer_config.shared["schema_version"],
         "config_sha256": peer_config.config_sha256()})

    assert agreement.agreed, agreement.mismatches


def test_a_nonce_can_be_pinned_so_both_peers_can_reproduce_the_signature(peer_config):
    """Needed to re-derive an agreement after the fact, e.g. in an audit."""
    service = NegotiationService(peer_config)
    first = service.handshake(nonce="a1a2a3a4b1b2b3b4c1c2c3c4d1d2d3d4")
    second = service.handshake(nonce="a1a2a3a4b1b2b3b4c1c2c3c4d1d2d3d4")
    assert first.signature == second.signature


def test_greeting_the_same_peer_twice_gives_the_same_agreement(peer_config):
    """``hello`` must be idempotent, and a fresh nonce per call broke that.

    An opponent may greet us more than once -- a retry, a reconnect, a
    readiness probe. If each answer carried a new nonce and signature, the
    agreement in the declaration artifact would not be the one we served a
    minute later, and neither of us could point at "the" agreement afterwards.
    Caught by our own server-binding tests, which compare two invocations.
    """
    service = NegotiationService(peer_config)
    assert service.handshake().as_dict() == service.handshake().as_dict()


def test_two_separate_peer_processes_do_not_share_a_nonce(peer_config):
    """Stable within a pairing, not a constant baked into the repository."""
    first = NegotiationService(peer_config).handshake()
    second = NegotiationService(peer_config).handshake()
    assert first.nonce != second.nonce
    assert first.terms == second.terms, "only the nonce moves"


def test_the_round_trip_through_the_wire_shape_preserves_the_agreement(peer_config):
    """``from_dict(as_dict(x))`` must still verify -- this is what crosses MCP."""
    ours = NegotiationService(peer_config).handshake()
    revived = Handshake.from_dict(ours.as_dict())

    assert revived.terms == ours.terms
    assert core_terms.signature_verifies(revived.terms, revived.nonce, revived.signature)
