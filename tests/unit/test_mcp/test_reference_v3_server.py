"""The three reference-v3 tools: validate, enqueue, return -- and never more.

The contract these tests defend is the kit's own: a handler that waits for game
progress puts two peers inside each other's handlers, which its transport module
calls the highest-severity failure available in the design. So the assertions
are as much about what does *not* happen -- no engine call, no reply turn, no
blocking -- as about the queue filling.

The other half is ordering. The vector requires the accept/refuse decision
before any state change, because a partially applied bad turn cannot be rolled
back and rule 35 zeroes both teams for a self-inflicted protocol fault. A
refused message must therefore leave the queue exactly as it found it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2pchase.mcp import contracts
from p2pchase.mcp.reference_v3_server import REFERENCE_TOOLS, Inboxes, register_reference_v3

VECTOR = json.loads(
    (Path(__file__).resolve().parents[2] / "fixtures" / "kit_turn_message_vector.json")
    .read_text(encoding="utf-8"))
GOOD = next(c["message"] for c in VECTOR["validation"] if c["verdict"] == "accept")
BAD = next(c["message"] for c in VECTOR["validation"] if c["verdict"] != "accept")
BAD_VERDICT = next(c["verdict"] for c in VECTOR["validation"] if c["verdict"] != "accept")


class _Recorder:
    """Stands in for FastMCP: keeps the decorated functions, by name."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, fn):
        self.tools[fn.__name__] = fn
        return fn


@pytest.fixture
def bound() -> tuple[dict, Inboxes]:
    mcp, inboxes = _Recorder(), Inboxes()
    register_reference_v3(mcp, inboxes)
    return mcp.tools, inboxes


def test_exactly_the_three_new_names_are_published(bound):
    tools, _ = bound
    assert set(tools) == set(REFERENCE_TOOLS)
    assert "negotiate" not in tools, "negotiate is ours already; a second binding would clash"


def test_the_published_names_match_the_advertised_contract():
    assert set(REFERENCE_TOOLS) == set(contracts.REFERENCE_V3_TOOLS)
    assert set(REFERENCE_TOOLS) <= set(contracts.PUBLISHED_TOOLS)


def test_the_argument_names_copy_the_references_own_asymmetry(bound):
    """`submit_audit` takes `payload`; the other two take `message`.

    Tidying this would be unreachable rather than clean -- FastMCP matches
    declared names only. Read off the functions so a rename cannot pass.
    """
    tools, _ = bound
    assert list(tools["receive_turn"].__code__.co_varnames[:1]) == ["message"]
    assert list(tools["receive_control"].__code__.co_varnames[:1]) == ["message"]
    assert list(tools["submit_audit"].__code__.co_varnames[:1]) == ["payload"]


def test_a_good_turn_is_queued_and_acknowledged(bound):
    tools, inboxes = bound
    assert tools["receive_turn"](GOOD) == {"ok": True}
    assert len(inboxes.turns) == 1
    assert inboxes.turns[0]["commit"] == GOOD["commit"]


def test_a_refused_turn_never_reaches_the_queue(bound):
    """Validate before enqueue. The whole ordering rule, in one assertion."""
    tools, inboxes = bound
    answer = tools["receive_turn"](BAD)
    assert answer["ok"] is False
    assert answer["error"] == BAD_VERDICT
    assert not inboxes.turns


def test_a_refusal_is_recorded_rather_than_vanishing(bound):
    """Their handlers answer ok unconditionally, so a refusal leaves no trace.

    Recording it does not stop the stall, but it turns "the series hung" into a
    line naming the field.
    """
    tools, inboxes = bound
    tools["receive_turn"](BAD)
    assert inboxes.refusals == [BAD_VERDICT]


def test_the_queued_turn_is_a_copy_the_caller_cannot_mutate(bound):
    """An opponent holds a reference to what it sent us; we must not share it."""
    tools, inboxes = bound
    sent = dict(GOOD)
    tools["receive_turn"](sent)
    sent["step"] = 999
    assert inboxes.turns[0]["step"] == GOOD["step"]


def test_an_audit_is_queued_under_its_own_name(bound):
    tools, inboxes = bound
    payload = {"sender": "thief", "records": [{"step": 1}], "result_claim": "capture"}
    assert tools["submit_audit"](payload) == {"ok": True}
    assert len(inboxes.audits) == 1
    assert not inboxes.turns, "an audit must not land in the turn queue"


def test_a_malformed_audit_is_refused_without_queueing(bound):
    tools, inboxes = bound
    assert tools["submit_audit"]({"sender": "thief"})["ok"] is False
    assert not inboxes.audits


def test_control_is_accepted_without_being_interpreted(bound):
    """Optional, unsealed, unscored -- answered rather than acted on."""
    tools, inboxes = bound
    assert tools["receive_control"]({"kind": "status", "sender": "thief"}) == {"ok": True}
    assert len(inboxes.controls) == 1


def test_a_control_message_that_is_not_an_object_does_not_raise(bound):
    tools, inboxes = bound
    assert tools["receive_control"]("nonsense") == {"ok": True}
    assert list(inboxes.controls) == [{}]


def test_clearing_drops_queued_messages_but_keeps_the_refusal_log(bound):
    """Between sub-games: the next peer's push is not this sub-game's business.

    Refusals survive on purpose -- they are the diagnosis of a series, not state
    belonging to one sub-game of it.
    """
    tools, inboxes = bound
    tools["receive_turn"](GOOD)
    tools["receive_turn"](BAD)
    inboxes.clear()
    assert not inboxes.turns
    assert inboxes.refusals == [BAD_VERDICT]

