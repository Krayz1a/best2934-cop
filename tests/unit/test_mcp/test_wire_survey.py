"""The pre-flight that would have made 2026-08-08 a ten-second finding.

Two teams agreed fourteen hashed terms, three lock digests and a signature
scheme, then discovered at the T that their surfaces shared one tool name and
that the shared one spelled its argument differently. Nothing in either
pre-flight looked at the surface at all.

``drivable`` is deliberately "at least one name we can call", never "all of
ours". A reference-v3 peer publishes four names and is entirely playable through
an adapter; demanding our whole surface would refuse every opponent in the
league who did not copy our implementation.
"""

from __future__ import annotations

from types import SimpleNamespace

from p2pchase.mcp.wire_survey import ToolSurface, compare, survey_text

OURS = {"hello", "negotiate", "commit_step", "reveal_step"}
INTEROP = {"propose_config", "submit_turn"}

#: Exactly what imreeyal published at 19:00 on 2026-08-08.
REFERENCE_V3 = [ToolSurface("negotiate", ("message",), ("message",)),
                ToolSurface("receive_turn", ("message",), ("message",)),
                ToolSurface("submit_audit", ("payload",), ("payload",)),
                ToolSurface("receive_control", ("message",))]


def test_a_reference_v3_peer_is_drivable_through_the_one_shared_name():
    survey = compare(REFERENCE_V3, OURS, INTEROP)
    assert survey.drivable
    assert [s.name for s in survey.shared] == ["negotiate"]
    assert [s.name for s in survey.theirs_only] == [
        "receive_control", "receive_turn", "submit_audit"]


def test_the_argument_asymmetry_is_reported_not_flattened():
    """`submit_audit` takes `payload` while the other three take `message`.

    The reference's own inconsistency, and the single most likely thing to be
    got wrong by an implementer reading only tool names.
    """
    by_name = {s.name: s for s in REFERENCE_V3}
    assert by_name["receive_turn"].arguments == ("message",)
    assert by_name["submit_audit"].arguments == ("payload",)


def test_a_peer_with_no_shared_names_is_not_drivable():
    survey = compare([ToolSurface("receive_turn"), ToolSurface("submit_audit")], OURS, INTEROP)
    assert not survey.drivable
    assert survey.shared == []


def test_an_empty_surface_is_not_drivable():
    assert not compare([], OURS, INTEROP).drivable


def test_our_own_absent_names_are_listed_without_being_a_failure():
    """Absence is information, never a refusal -- the league's omission rule."""
    survey = compare(REFERENCE_V3, OURS, INTEROP)
    assert "hello" in survey.ours_only
    assert survey.drivable


def test_from_tool_reads_argument_names_out_of_the_json_schema():
    tool = SimpleNamespace(name="negotiate", inputSchema={
        "properties": {"message": {}, "handshake": {}}, "required": ["message"]})
    surface = ToolSurface.from_tool(tool)
    assert surface.name == "negotiate"
    assert surface.arguments == ("handshake", "message")
    assert surface.required == ("message",)


def test_a_tool_publishing_no_schema_is_reported_rather_than_skipped():
    """"We could not tell" and "it takes nothing" look alike and both matter."""
    surface = ToolSurface.from_tool(SimpleNamespace(name="mystery", inputSchema=None))
    assert surface.name == "mystery"
    assert surface.arguments == ()


def test_a_snake_case_schema_attribute_is_also_read():
    tool = SimpleNamespace(name="t", input_schema={"properties": {"payload": {}}})
    assert ToolSurface.from_tool(tool).arguments == ("payload",)


def test_the_report_says_cannot_play_when_nothing_is_shared():
    text, drivable = survey_text("http://peer/mcp", [ToolSurface("receive_turn")],
                                 OURS, INTEROP)
    assert not drivable
    assert "CANNOT PLAY" in text
    assert "not one tool name in common" in text


def test_the_report_names_the_argument_spellings_when_it_can_play():
    text, drivable = survey_text("http://peer/mcp", REFERENCE_V3, OURS, INTEROP)
    assert drivable
    assert "CAN PLAY" in text
    assert "negotiate" in text and "message" in text
    assert "receive_turn" in text, "a tool we cannot drive must still be shown"
