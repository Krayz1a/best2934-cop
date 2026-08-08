"""Conformance to the kit's published reference-v3 vector.

``tests/fixtures/kit_turn_message_vector.json`` is the kit's own
``vectors/turn_message.json``, vendored unmodified. Its seven cases each carry
an expected verdict, and :func:`refuse_turn` returns that verdict's text
verbatim -- so the vector is the oracle and this file only drives it.

That is deliberate and it is the lesson of the last two days. A test that
restates an expectation in its own words is a second copy of the contract, and
a second copy drifts. We spent an evening on a wire where both sides had
paraphrased each other correctly about everything except the one thing that
mattered.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2pchase.mcp import reference_v3

VECTOR = json.loads(
    (Path(__file__).resolve().parents[2] / "fixtures" / "kit_turn_message_vector.json")
    .read_text(encoding="utf-8"))
CASES = VECTOR["validation"]
ACCEPTED = next(c["message"] for c in CASES if c["verdict"] == "accept")


def test_the_vendored_vector_is_the_promoted_one():
    """A downgraded or draft vector would make every assertion below meaningless."""
    assert VECTOR["status"] == "PROMOTED"
    assert len(CASES) == 7


@pytest.mark.parametrize("case", CASES, ids=[c["verdict"][:28] for c in CASES])
def test_every_published_case_gets_the_published_verdict(case):
    refusal = reference_v3.refuse_turn(case["message"])
    expected = "" if case["verdict"] == "accept" else case["verdict"]
    assert refusal == expected, case["note"]


def test_an_unknown_key_is_tolerated_and_then_dropped():
    """Tolerate means ignore, not forward. The vector requires the first."""
    message = dict(ACCEPTED, unknown_field={"anything": 1})
    assert reference_v3.refuse_turn(message) == ""
    assert "unknown_field" not in reference_v3.to_internal(message)


def test_a_boolean_intensity_is_refused_rather_than_read_as_one():
    """``True`` is an ``int`` in Python, so a naive numeric check passes it.

    That is worse than a refusal: it becomes an intensity of 1.0 and quietly
    wrong trail evidence, which no audit would catch as a protocol fault.
    """
    message = dict(ACCEPTED, smell_grid={"3,3": True})
    assert reference_v3.refuse_turn(message) == "smell_grid: required dict of 'r,c' -> number"


def test_a_boolean_step_is_not_a_step():
    assert reference_v3.refuse_turn(dict(ACCEPTED, step=True)) == \
        "step: required non-negative int"


def test_a_sender_that_is_neither_role_is_refused():
    assert reference_v3.refuse_turn(dict(ACCEPTED, sender="cop")) == \
        "sender: required 'police' or 'thief'"


def test_a_message_that_is_not_an_object_is_refused_rather_than_raising():
    assert reference_v3.refuse_turn("not a message") == "message: required object"
    assert reference_v3.refuse_turn(None) == "message: required object"


def test_translation_renames_the_grid_and_keeps_the_numbers():
    internal = reference_v3.to_internal(ACCEPTED)
    assert internal["scent_grid"] == {"3,3": 0.9, "3,4": 0.5, "4,3": 0.5}
    assert "smell_grid" not in internal
    assert internal["step"] == ACCEPTED["step"]
    assert internal["commit"] == ACCEPTED["commit"]


def test_translation_drops_the_timestamp_because_nothing_reads_it():
    assert "timestamp" not in reference_v3.to_internal(ACCEPTED)


def test_a_round_trip_through_both_directions_is_accepted_again():
    """The strongest single check: what we emit must satisfy their validator."""
    internal = reference_v3.to_internal(ACCEPTED)
    theirs = reference_v3.from_internal(internal, timestamp="2026-08-08T19:00:00Z")
    assert reference_v3.refuse_turn(theirs) == ""
    assert theirs["smell_grid"] == ACCEPTED["smell_grid"]
    assert theirs["sender"] == ACCEPTED["sender"]


def test_what_we_emit_carries_a_timestamp_the_caller_supplied():
    theirs = reference_v3.from_internal(reference_v3.to_internal(ACCEPTED), timestamp="t")
    assert theirs["timestamp"] == "t"


def test_an_empty_timestamp_makes_our_own_turn_refusable():
    """Pinning the failure mode the kit's own sparring peer ships with."""
    theirs = reference_v3.from_internal(reference_v3.to_internal(ACCEPTED), timestamp="")
    assert reference_v3.refuse_turn(theirs) == "timestamp: required non-empty str"


def test_the_optional_fields_survive_the_round_trip():
    internal = reference_v3.to_internal(dict(ACCEPTED, capture_claim=[2, 2]))
    assert internal["capture_claim"] == [2, 2]
    assert reference_v3.from_internal(internal, "t")["capture_claim"] == [2, 2]


def test_an_audit_payload_is_shaped_as_the_vector_requires():
    payload = reference_v3.audit_from_records("THIEF", [{"step": 1}], "capture")
    assert reference_v3.refuse_audit(payload) == ""
    assert payload["sender"] == "thief"
    assert payload["result_claim"] == "capture"
    for name in VECTOR["audit_payload"]["required"]:
        assert name in payload


def test_an_audit_without_records_is_refused():
    assert reference_v3.refuse_audit({"sender": "thief", "result_claim": "x"}) == \
        "records: required list of sealed records"
