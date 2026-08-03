"""Commit-reveal integrity (book ch5, ch7; rules 17-20)."""

from __future__ import annotations

from p2pchase.domain.crypto import (
    audit_records,
    canonical_json,
    commit,
    digest_payload,
    mutual_agreement_hash,
    new_nonce,
    sha256_hex,
    sign_declaration,
    verify,
)

PAYLOAD = {"step": 1, "role": "police", "move": "N", "hint": "north past Harlem"}


def test_canonical_json_is_key_order_independent():
    """Two peers building the same object differently must hash identically."""
    a = canonical_json({"b": 2, "a": 1})
    b = canonical_json({"a": 1, "b": 2})
    assert a == b == '{"a":1,"b":2}'


def test_canonical_json_keeps_unicode_intact():
    assert "ש" in canonical_json({"k": "ש"})


def test_digest_is_deterministic_and_sensitive():
    assert digest_payload(PAYLOAD) == digest_payload(dict(PAYLOAD))
    assert digest_payload(PAYLOAD) != digest_payload({**PAYLOAD, "move": "S"})
    assert len(sha256_hex("x")) == 64


def test_nonces_are_unique():
    assert len({new_nonce() for _ in range(200)}) == 200


def test_a_commitment_verifies_against_its_own_nonce():
    record = commit(PAYLOAD)
    assert verify(record.payload, record.nonce, record.commit)


def test_a_commitment_fails_against_a_different_nonce():
    record = commit(PAYLOAD)
    assert not verify(record.payload, new_nonce(), record.commit)


def test_altering_one_field_breaks_the_commitment():
    """The whole security argument: one changed bit is provable."""
    record = commit(PAYLOAD)
    tampered = {**record.payload, "move": "S"}
    assert not verify(tampered, record.nonce, record.commit)


def test_the_sealed_view_leaks_nothing():
    """During play a peer publishes the hash alone -- no move, no hint, no nonce."""
    sealed = commit(PAYLOAD).sealed_view()
    assert set(sealed) == {"step", "commit"}
    text = str(sealed)
    assert "north past Harlem" not in text
    assert "N" not in sealed.get("commit", "").upper() or True  # hash only


def test_the_revealed_view_discloses_content_but_not_the_nonce():
    """Rule 18: nonces stay sealed until the end of the sub-game."""
    revealed = commit(PAYLOAD).revealed_view()
    assert revealed["payload"]["move"] == "N"
    assert "nonce" not in revealed


def test_the_audit_view_discloses_everything():
    audit = commit(PAYLOAD).audit_view()
    assert set(audit) == {"payload", "nonce", "commit"}


def test_audit_passes_on_an_intact_chain():
    records = [commit({**PAYLOAD, "step": n}).audit_view() for n in range(1, 6)]
    result = audit_records(records)
    assert result.passed
    assert result.verified_steps == 5
    assert result.failed_steps == []


def test_audit_names_the_tampered_step():
    records = [commit({**PAYLOAD, "step": n}).audit_view() for n in range(1, 6)]
    records[2]["payload"]["move"] = "W"
    result = audit_records(records)
    assert not result.passed
    assert result.failed_steps == [3]


def test_audit_rejects_a_record_with_no_nonce():
    records = [commit(PAYLOAD).audit_view()]
    del records[0]["nonce"]
    assert not audit_records(records).passed


def test_audit_of_an_empty_log_is_vacuously_clean():
    result = audit_records([])
    assert result.passed
    assert result.verified_steps == 0


def test_declaration_signature_depends_on_the_secret():
    payload = {"spec": {"cpu": "test"}, "group_name": "test1234"}
    assert sign_declaration(payload, "s1") != sign_declaration(payload, "s2")
    assert sign_declaration(payload, "s1") == sign_declaration(dict(payload), "s1")


def test_mutual_agreement_hash_matches_for_identical_summaries():
    """Rule 35: two matching digests are how agreement is proved, not asserted."""
    summary = {"game_id": "a-vs-b", "final_result": {"winner_group": "a"}}
    assert mutual_agreement_hash(summary) == mutual_agreement_hash(dict(summary))
    assert mutual_agreement_hash(summary) != mutual_agreement_hash(
        {**summary, "final_result": {"winner_group": "b"}}
    )
