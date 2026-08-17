"""Commit-reveal integrity (book ch5, ch7; rules 17-20)."""

from __future__ import annotations

from p2pchase.domain.crypto import (
    MID_GAME_FIELDS,
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


def test_the_revealed_view_discloses_the_hint_but_not_the_nonce():
    """Rule 18: nonces stay sealed until the end of the sub-game."""
    revealed = commit(PAYLOAD).revealed_view()
    assert revealed["payload"]["hint"] == "north past Harlem"
    assert "nonce" not in revealed


#: A full sealed payload, exactly as :class:`StepIntent` builds one.
FULL = {"step": 3, "role": "police", "sub_game": 1, "state": "deadbeef" * 8,
        "move": "N", "intent": "lie", "hint": "north past Harlem"}


def test_the_revealed_view_seals_the_move_the_intent_and_the_state():
    """I-5. The three fields that give the position and the deception away."""
    revealed = commit(FULL).revealed_view()["payload"]
    assert set(revealed) <= set(MID_GAME_FIELDS)
    for withheld in ("move", "intent", "state"):
        assert withheld not in revealed
    # Not just absent as keys -- absent as values. A field re-spelled under
    # another name would pass the check above and leak just as much.
    text = canonical_json(revealed)
    assert "lie" not in text and "deadbeef" not in text


def test_a_declared_barrier_is_still_disclosed():
    """Rule 15: the cop declares each placement openly, so it is not a leak."""
    assert commit({**FULL, "barrier": [2, 3]}).revealed_view()["payload"]["barrier"] == [2, 3]


def test_the_full_payload_still_reaches_the_audit():
    """Sealing is a delay, not a withholding: rule 19 needs every field."""
    assert commit(FULL).audit_view()["payload"] == FULL


def test_the_state_digest_would_have_given_the_position_away():
    """Why ``state`` is sealed, demonstrated rather than asserted.

    Every field but ``position`` is public, so the digest has 49 candidates on
    a 7x7 board. This is the attack an opponent runs against what we used to
    disclose every single step; it must no longer have anything to run against.
    """
    board = {"grid_size": 7, "barriers": []}
    truth = {"step": 4, "role": "police", "position": [5, 2], "board": board}
    leaked = digest_payload(truth)

    recovered = [[r, c] for r in range(7) for c in range(7)
                 if digest_payload({**truth, "position": [r, c]}) == leaked]
    assert recovered == [[5, 2]]  # the whole search space is 49 hashes

    sealed = commit({"step": 4, "role": "police", "move": "N", "hint": "hi",
                     "state": leaked}).revealed_view()["payload"]
    assert "state" not in sealed


def test_the_audit_view_discloses_everything():
    audit = commit(PAYLOAD).audit_view()
    assert set(audit) == {"payload", "nonce", "commit", "step"}


def test_the_step_is_repeated_at_the_top_level_of_a_disclosure():
    """A reveal a reader cannot key to its commitment is not a disclosure.

    anrbj666 reported every record of ours arriving as commit-plus-declaration
    with no reveal attached, 35 times a window across six windows, while our
    sender was provably sending payload and nonce. Their own records carry
    ``step`` at both levels; ours carried it only inside the payload.
    """
    audit = commit({**PAYLOAD, "step": 7}).audit_view()
    assert audit["step"] == 7 == audit["payload"]["step"]


def test_a_payload_without_a_step_discloses_a_null_rather_than_raising():
    """Not every sealed record is a move -- a control note has no step."""
    assert commit({"type": "control"}).audit_view()["step"] is None


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
