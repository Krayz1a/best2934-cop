"""The kit's CORE agreement, checked against the kit's own published vector.

The vector is reproduced here as a literal rather than fetched, so the test
fails if *our* construction moves. Its values are the kit's
``vectors/terms_signature.json`` (status: CORE), copied by hand.

Why this file exists: our handshake published nine fields about ourselves and
none of the terms, so imreeyal's gate refused it and ours refused theirs, and
the friendly could not start in either direction.
"""

from __future__ import annotations

import json

from p2pchase.domain import core_terms

#: ``vectors/terms_signature.json``, the single CORE vector, verbatim.
KIT_TERMS = {
    "board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1,
    "emit_intensity": 0.9, "min_center_intensity": 0.5, "max_steps": 35,
    "barriers_max": 14, "setting": "Haifa", "hint_max_words": 15,
    "axis_origin_corner": "top-left", "axis_start_index": 0,
    "thief_start": [3, 3], "cop_start": [0, 0], "num_games": 1,
}
KIT_NONCE = "a1a2a3a4b1b2b3b4c1c2c3c4d1d2d3d4"
KIT_SIGNATURE = "80793141f22b6193b02a74d5955767ad1e24abbac172894358ec13622b85a04c"


def test_we_reproduce_the_kit_core_signature_vector():
    """The whole gate in one assertion: their published number, our code."""
    assert core_terms.sign_terms(KIT_TERMS, KIT_NONCE) == KIT_SIGNATURE


def test_the_separator_is_one_pipe_and_the_alternatives_are_wrong():
    """Pinning the ambiguity that would have cost us the pairing silently.

    The kit writes ``SHA256(canonical_json(terms)|nonce)``; it was restated to
    us as ``... || nonce``, which reads as either a C-style concatenation or a
    literal double pipe. All three are plausible from prose and only one
    reproduces the vector, so the reading is pinned rather than remembered.
    """
    from p2pchase.domain.crypto import canonical_json, sha256_hex

    body = canonical_json(KIT_TERMS)
    assert sha256_hex(body + KIT_NONCE) != KIT_SIGNATURE, "bare concatenation"
    assert sha256_hex(f"{body}||{KIT_NONCE}") != KIT_SIGNATURE, "double pipe"
    assert sha256_hex(f"{body}|{KIT_NONCE}") == KIT_SIGNATURE


def test_the_float_survives_serialisation_as_the_shortest_repr():
    """The vector's stated trap: ``0.1`` must not become ``0.10000000000000001``.

    A language that widens it fails the signature and cannot play at all -- the
    kit says so in the vector's own description, and it costs nothing to prove
    rather than assume our serialiser is one of the ones that behaves.
    """
    body = json.loads(core_terms.canonical_json(KIT_TERMS))
    assert core_terms.canonical_json(KIT_TERMS).count("0.1,") == 1
    assert body["decay_per_step"] == 0.1


def test_our_terms_carry_exactly_the_fourteen_core_keys(shared_config):
    """Not thirteen and not fifteen: the set is part of the digest."""
    terms = core_terms.core_terms(shared_config)
    assert set(terms) == set(core_terms.CORE_KEYS)
    assert len(core_terms.CORE_KEYS) == 14


def test_our_terms_are_read_from_the_config_that_governs_play(shared_config):
    """A signature over values we do not run would be worse than none at all."""
    terms = core_terms.core_terms(shared_config)
    assert terms["board_size"] == shared_config["board_and_agents"]["grid_size"]
    assert terms["barriers_max"] == shared_config["movement_and_barriers"]["max_barriers"]
    assert terms["setting"] == shared_config["world"]["map_area"]
    assert terms["num_games"] == shared_config["network_and_league"]["num_sub_games"]
    # max_steps reads survival_threshold, not max_moves. They are equal at 35,
    # which is exactly why the choice needs pinning: nothing would catch it.
    assert terms["max_steps"] == shared_config["movement_and_barriers"]["survival_threshold"]


def test_our_own_agreement_verifies_against_itself(shared_config):
    agreement = core_terms.signed_agreement(shared_config)
    assert core_terms.signature_verifies(
        agreement["terms"], agreement["nonce"], agreement["signature"])


def test_a_fresh_nonce_is_used_when_none_is_given(shared_config):
    """Two agreements must not be replayable one for the other."""
    first = core_terms.signed_agreement(shared_config)
    second = core_terms.signed_agreement(shared_config)
    assert first["nonce"] != second["nonce"]
    assert first["signature"] != second["signature"]
    assert first["terms"] == second["terms"], "only the nonce moves"


def test_an_unsigned_or_mis_signed_agreement_does_not_verify():
    assert not core_terms.signature_verifies(KIT_TERMS, KIT_NONCE, "")
    assert not core_terms.signature_verifies(KIT_TERMS, "different-nonce", KIT_SIGNATURE)
    tampered = {**KIT_TERMS, "barriers_max": 15}
    assert not core_terms.signature_verifies(tampered, KIT_NONCE, KIT_SIGNATURE)


def test_every_differing_term_is_reported_not_just_the_first():
    """A pairing that fixes one term per round trip spends its window on this."""
    theirs = {**KIT_TERMS, "barriers_max": 15, "setting": "Tel Aviv", "num_games": 6}
    differences = core_terms.term_differences(KIT_TERMS, theirs)
    assert len(differences) == 3
    assert any("barriers_max" in line for line in differences)
    assert any("setting" in line for line in differences)


def test_a_missing_core_key_is_a_difference_rather_than_an_omission():
    """The CORE set is fixed, so a short agreement is malformed, not silent.

    The omission rule protects fields we invented and others may never have
    heard of. These fourteen are not those -- the kit defines them and the
    signature is computed over all of them.
    """
    short = {key: value for key, value in KIT_TERMS.items() if key != "cop_start"}
    assert core_terms.term_differences(KIT_TERMS, short) == [
        "terms.cop_start: ours=[0, 0] theirs=None"]
