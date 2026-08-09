"""Two peers can agree everything and still fail every step of the audit.

On 2026-08-09 we played imreeyal six sub-games end to end -- handshake, 35
rounds, mutual submit_audit, four artifacts each -- and audited **0 of 36
steps** in every one, with ``forged_steps`` and ``withheld_steps`` both empty.
Nothing was rewritten and nothing was omitted. Every step arrived and every
step failed to re-hash.

The cause was not a disagreement about the game. It was a disagreement about
how a commitment is *built*:

    ours  sha256(canonical_json({**payload, "nonce": nonce}))
    kit   sha256(canonical_json(payload) + "|" + nonce)

The evidence that they use the kit's, rather than merely that the kit
documents it: had they used ours, our audit of their chain would have passed.
It failed on all 36. Our own data rules out the alternative.

That is the shape of failure worth a test file of its own -- a whole series
that looks flawless until a report is due, which under rule 35 voids the
sub-game for both teams when the two audits disagree.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2pchase.domain import kit_seal
from p2pchase.domain.crypto import canonical_json, commit, sha256_hex, verify
from p2pchase.shared.peer_config import PeerConfig

REPO = Path(__file__).resolve().parents[3]
PAYLOAD = {"step": 7, "role": "police", "move": "N", "hint": "north"}
NONCE = "0123456789abcdef"


def _config(role: str = "police") -> PeerConfig:
    read = lambda name: json.loads(  # noqa: E731 -- two reads, one shape
        (REPO / "config" / role / name).read_text(encoding="utf-8"))
    return PeerConfig(role=role, shared=read("game.json"), setup=read("setup.json"))


# ------------------------------------------------------- the two constructions
def test_the_kit_form_is_a_single_pipe_not_a_merged_key():
    """Spelled out against the literal bytes, not against our own helper."""
    expected = sha256_hex(canonical_json(PAYLOAD) + "|" + NONCE)
    assert kit_seal.seal(PAYLOAD, NONCE, kit_seal.PIPE) == expected


def test_our_form_merges_the_nonce_into_the_payload():
    expected = sha256_hex(canonical_json({**PAYLOAD, "nonce": NONCE}))
    assert kit_seal.seal(PAYLOAD, NONCE, kit_seal.MERGED) == expected


def test_the_two_forms_disagree():
    """The whole defect in one assertion."""
    assert (kit_seal.seal(PAYLOAD, NONCE, kit_seal.MERGED)
            != kit_seal.seal(PAYLOAD, NONCE, kit_seal.PIPE))


def test_an_unknown_form_falls_back_to_ours_rather_than_raising():
    """A typo in a config must not forfeit a live sub-game under rule 6."""
    assert kit_seal.seal(PAYLOAD, NONCE, "not-a-form") == kit_seal.seal(
        PAYLOAD, NONCE, kit_seal.MERGED)


# ------------------------------------------------- verification takes either
@pytest.mark.parametrize("form", kit_seal.FORMS)
def test_verify_accepts_every_registered_form(form):
    """Seal in one spelling, audit in the other, and nothing fails."""
    assert verify(PAYLOAD, NONCE, kit_seal.seal(PAYLOAD, NONCE, form))


def test_verify_still_refuses_a_commitment_that_opens_to_neither():
    assert not verify(PAYLOAD, NONCE, "f" * 64)


def test_verify_refuses_a_rewritten_payload_under_both_forms():
    """Generosity about spelling must not become generosity about content."""
    for form in kit_seal.FORMS:
        sealed = kit_seal.seal(PAYLOAD, NONCE, form)
        assert not verify({**PAYLOAD, "move": "S"}, NONCE, sealed)


def test_verify_refuses_the_right_payload_under_the_wrong_nonce():
    for form in kit_seal.FORMS:
        assert not verify(PAYLOAD, "beef", kit_seal.seal(PAYLOAD, NONCE, form))


# --------------------------------------------------- sealing is per pairing
def test_imreeyal_is_sealed_in_the_kit_form():
    assert _config().seal_form("imreeyal") == kit_seal.PIPE


def test_gal_roy1_is_still_sealed_in_ours():
    """They audit our chains under our construction and it works. Do not break it."""
    assert _config().seal_form("gal-roy1") == kit_seal.MERGED


def test_an_undeclared_opponent_gets_ours():
    assert _config().seal_form("a-team-we-have-never-met") == kit_seal.MERGED


@pytest.mark.parametrize("role", ["police", "thief"])
def test_both_roles_declare_the_same_form_for_one_opponent(role):
    """A pairing term that differed by our own role would desync mid-series."""
    assert _config(role).seal_form("imreeyal") == kit_seal.PIPE


# ------------------------------------------------------------- the seal call
def test_commit_defaults_to_our_form_so_existing_artifacts_stay_valid():
    assert commit(PAYLOAD, NONCE).commit == kit_seal.seal(PAYLOAD, NONCE, kit_seal.MERGED)


def test_commit_honours_the_named_form():
    record = commit(PAYLOAD, NONCE, form=kit_seal.PIPE)
    assert record.commit == kit_seal.seal(PAYLOAD, NONCE, kit_seal.PIPE)


def test_a_record_sealed_in_the_kit_form_audits_clean():
    """End to end: seal as we now do for imreeyal, verify as they will."""
    record = commit(PAYLOAD, form=kit_seal.PIPE).audit_view()
    assert verify(record["payload"], record["nonce"], record["commit"])
