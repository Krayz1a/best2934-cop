"""The round count: carried in the dataclass, reported in the LOG summary only.

Getting the *number* right was the hard part. The old log summary derived it as
``len(records) - 1``, which encodes two assumptions: exactly one non-game record
at the front, and exactly one record per round. On the reference-v3 wire neither
holds. There is no step-0 record to subtract, and a conceding thief seals a
terminal ``STAY`` that makes the chain one longer than the game. The two errors
point in opposite directions and only one applies at a time, so they never
cancel -- a 35-round sub-game would have been reported as 34 or 36 depending on
how it ended, against an opponent who counted the same game correctly.

Getting the *place* right came second. We first put it in the result artifact's
sub-game row, on imreeyal's request. They then withdrew the request: the course
result template's sub-game row does not carry it. What they missed is that the
template's **log** summary does -- ``steps`` sits between ``winner_role`` and
``timezone`` -- so the field is mandatory, it simply lives in the other file.
Dropping it outright, which is what they proposed for both sides, would diverge
from the template rather than match it.
"""

from __future__ import annotations

import json
import pathlib

from p2pchase.domain.scoring import build_score_table
from p2pchase.reports import artifacts
from p2pchase.reports.series_assembly import assemble_series

FIXTURE = pathlib.Path(__file__).resolve().parents[2] / \
    "fixtures/course_template_fields.json"


def _template() -> dict[str, list[str]]:
    """Field names lifted from the course's own sample run. See the fixture."""
    return json.loads(FIXTURE.read_text())


#: The course reference sample's sub-game row, field for field and in order.
TEMPLATE_ROW = ["sub_game_number", "roles", "started_at", "ended_at", "result",
                "winner_group", "tie", "github_commit", "tokens", "score",
                "log_files", "audit"]


def _records(count: int) -> list[dict[str, object]]:
    return [{"commit": f"c{n}", "nonce": f"n{n}", "payload": {"step": n}}
            for n in range(count)]


def _row(steps: int = 0) -> artifacts.SubGameOutcome:
    return artifacts.SubGameOutcome(
        sub_game_number=1, roles={"a": "police", "b": "thief"}, started_at="s",
        ended_at="e", result="capture", winner_group="a", github_commit={},
        tokens={}, score={"a": 20, "b": 5}, log_files={}, audit={}, steps=steps)


# ------------------------------------------- the number, in the log summary
def test_the_caller_s_round_count_wins_over_the_chain_length():
    body = artifacts.build_log_artifact(
        "a-vs-b", "uid", 1, "a", "police", "b", "capture", "police", _records(37),
        "s", "e", 0, {}, steps=35)
    assert body["summary"]["steps"] == 35


def test_a_conceded_sub_game_is_not_reported_one_round_long():
    """36 disclosed records, 35 rounds played. This is the live case."""
    body = artifacts.build_log_artifact(
        "a-vs-b", "uid", 1, "a", "thief", "b", "capture", "police", _records(36),
        "s", "e", 0, {}, steps=35)
    assert body["summary"]["steps"] == 35


def test_a_chain_with_no_step_zero_is_not_reported_one_round_short():
    """The reference-v3 path discloses game steps only -- nothing to subtract."""
    body = artifacts.build_log_artifact(
        "a-vs-b", "uid", 1, "a", "police", "b", "survival", "thief", _records(35),
        "s", "e", 0, {}, steps=35)
    assert body["summary"]["steps"] == 35


def test_the_log_summary_carries_steps_because_the_template_does():
    """The field imreeyal proposed both sides drop. The template requires it."""
    body = artifacts.build_log_artifact(
        "a-vs-b", "uid", 1, "a", "police", "b", "capture", "police", _records(18),
        "s", "e", 0, {}, steps=17)
    assert "steps" in body["summary"]


# ------------------------------------- and NOT in the result sub-game row
def test_the_result_row_is_exactly_the_template_row():
    """No steps, no extras, same order. Checked against the field list itself."""
    assert list(_row(17).as_dict()) == TEMPLATE_ROW


def test_the_result_row_omits_steps_even_when_the_outcome_carries_one():
    assert "steps" not in _row(35).as_dict()


def test_the_outcome_still_carries_the_count_for_the_log_builder():
    """Dropping it from the row must not drop it from the object."""
    assert _row(35).steps == 35


def test_the_series_rebuild_carries_steps_out_of_the_logs():
    """The networked result is reassembled from disk, so it must read it back."""
    log = {"_filename": "log_a-vs-b_g01.json",
           "summary": {"sub_game_number": 1, "role": "police", "result": "capture",
                       "winner_role": "police", "steps": 12, "tokens_total": 0}}
    outcomes, _final, _tokens = assemble_series([log], "a", "b", build_score_table({}))
    assert outcomes[0].steps == 12


def test_a_log_written_before_this_field_existed_reassembles_as_zero():
    log = {"_filename": "log_a-vs-b_g01.json",
           "summary": {"sub_game_number": 1, "role": "police", "result": "capture",
                       "winner_role": "police", "tokens_total": 0}}
    outcomes, _final, _tokens = assemble_series([log], "a", "b", build_score_table({}))
    assert outcomes[0].steps == 0


def test_the_round_count_cannot_move_the_agreement_digest():
    """Belt and braces: it is out of the row AND out of the rule 35 scope."""
    ours = artifacts.build_result_artifact("a-vs-b", "u", ["a", "b"], [_row(35)], {}, {})
    theirs = artifacts.build_result_artifact("a-vs-b", "u", ["a", "b"], [_row(36)], {}, {})
    assert ours["mutual_agreement"]["sha256"] == theirs["mutual_agreement"]["sha256"]


def test_the_template_row_constant_matches_the_course_sample():
    """Guards the constant above against being edited to fit a passing test.

    Not conditional on the fixture existing. A check that skips itself when its
    input is missing reports the same green as one that ran, which is the exact
    failure mode imreeyal described in their own auditor -- verified *present*
    rather than verified *active*.
    """
    assert _template()["result_sub_game_row"] == TEMPLATE_ROW

# ------------------------------- the fallback, pinned to the reference itself
REFERENCE = pathlib.Path(__file__).resolve().parents[2] / \
    "fixtures/reference_chain_shape.json"


def _reference_chain() -> tuple[list[dict[str, object]], int, int]:
    data = json.loads(REFERENCE.read_text())
    records = [{"commit": "c", "nonce": "n", "payload": row} for row in data["chain"]]
    return records, data["published_steps"], data["record_count"]


def test_the_fallback_reproduces_the_reference_sample_s_own_number():
    """The only artifact either team can appeal to. It publishes 17 over 19.

    imreeyal count ``len(session.records)`` and we counted ``len(records) - 1``.
    On this chain those give 19 and 18. Both are wrong, and ours was wrong in a
    way our own tests could not see, because every fixture we had written for
    the fallback happened to be the tidy shape it assumed.
    """
    records, published, count = _reference_chain()
    body = artifacts.build_log_artifact(
        "a-vs-b", "uid", 1, "a", "thief", "b", "capture", "police", records,
        "s", "e", 0, {})
    assert body["summary"]["steps"] == published
    assert body["summary"]["steps"] not in (count, count - 1)


def test_a_duplicated_terminal_step_does_not_add_a_round():
    """The reference chain seals two records at step 17 and still reports 17."""
    records = [{"commit": "c", "nonce": "n", "payload": {"step": n}}
               for n in (1, 2, 3, 3)]
    body = artifacts.build_log_artifact(
        "a-vs-b", "uid", 1, "a", "thief", "b", "survival", "thief", records,
        "s", "e", 0, {})
    assert body["summary"]["steps"] == 3


def test_a_step_zero_declaration_is_not_a_round():
    records = [{"commit": "c", "nonce": "n",
                "payload": {"step": 0, "type": "system_spec"}}] + \
              [{"commit": "c", "nonce": "n", "payload": {"step": n}} for n in (1, 2)]
    body = artifacts.build_log_artifact(
        "a-vs-b", "uid", 1, "a", "police", "b", "capture", "police", records,
        "s", "e", 0, {})
    assert body["summary"]["steps"] == 2


def test_an_interleaved_control_record_is_not_a_round():
    """uoh-sqak's shape: a control record numbered inside the game space."""
    records = [{"commit": "c", "nonce": "n", "payload": {"step": 1}},
               {"commit": "c", "nonce": "n",
                "payload": {"step": 1, "type": "control"}},
               {"commit": "c", "nonce": "n", "payload": {"step": 2}}]
    body = artifacts.build_log_artifact(
        "a-vs-b", "uid", 1, "a", "police", "b", "capture", "police", records,
        "s", "e", 0, {})
    assert body["summary"]["steps"] == 2
