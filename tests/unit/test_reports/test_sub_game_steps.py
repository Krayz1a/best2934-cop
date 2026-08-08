"""``sub_games[].steps``: the round count, and why it is not the chain length.

The kit example carries a per-sub-game step count and we did not, so a reader
of our result could not tell a capture on move 3 from one on move 34 without
opening the log. Adding it is trivial; getting the *number* right is not.

The old log summary derived it as ``len(records) - 1``, which encodes two
assumptions: exactly one non-game record at the front, and exactly one record
per round. On the reference-v3 wire neither holds. There is no step-0 record to
subtract, and a conceding thief seals a terminal ``STAY`` that makes the chain
one longer than the game. The two errors point in opposite directions and only
one applies at a time, so they never cancel -- a 35-round sub-game would have
been reported as 34 or 36 depending on how it ended, against an opponent who
counted the same game correctly.
"""

from __future__ import annotations

from p2pchase.domain.scoring import build_score_table
from p2pchase.reports import artifacts
from p2pchase.reports.series_assembly import assemble_series


def _records(count: int) -> list[dict[str, object]]:
    return [{"commit": f"c{n}", "nonce": f"n{n}", "payload": {"step": n}}
            for n in range(count)]


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


def test_the_old_derivation_survives_for_callers_that_cannot_say():
    """Not every caller knows the round count; the fallback must stay put."""
    body = artifacts.build_log_artifact(
        "a-vs-b", "uid", 1, "a", "police", "b", "survival", None, _records(4),
        "s", "e", 0, {})
    assert body["summary"]["steps"] == 3


def test_the_result_row_reports_the_steps_it_was_given():
    row = artifacts.SubGameOutcome(
        sub_game_number=1, roles={"a": "police", "b": "thief"}, started_at="s",
        ended_at="e", result="capture", winner_group="a", github_commit={},
        tokens={}, score={}, log_files={}, audit={}, steps=17,
    )
    assert row.as_dict()["steps"] == 17


def test_a_row_built_without_steps_says_zero_rather_than_omitting_the_key():
    """A missing key and a zero read differently to a diffing opponent."""
    row = artifacts.SubGameOutcome(
        sub_game_number=1, roles={}, started_at="s", ended_at="e", result="survival",
        winner_group=None, github_commit={}, tokens={}, score={}, log_files={}, audit={},
    )
    assert row.as_dict()["steps"] == 0


def test_the_series_rebuild_carries_steps_out_of_the_logs():
    """The networked result is reassembled from disk, so it must read it back."""
    log = {"_filename": "log_a-vs-b_g01.json",
           "summary": {"sub_game_number": 1, "role": "police", "result": "capture",
                       "winner_role": "police", "steps": 12, "tokens_total": 0}}
    outcomes, _final, _tokens = assemble_series([log], "a", "b", build_score_table({}))
    assert outcomes[0].as_dict()["steps"] == 12


def test_a_log_written_before_this_field_existed_reassembles_as_zero():
    log = {"_filename": "log_a-vs-b_g01.json",
           "summary": {"sub_game_number": 1, "role": "police", "result": "capture",
                       "winner_role": "police", "tokens_total": 0}}
    outcomes, _final, _tokens = assemble_series([log], "a", "b", build_score_table({}))
    assert outcomes[0].as_dict()["steps"] == 0


def test_steps_is_outside_the_agreement_digest():
    """Deliberate: it is reported, not agreed.

    Two peers can legitimately count the same sub-game's length differently at
    the edges (whose terminal message landed, who saw the last round). That is
    worth showing a human and is not worth voiding a match over, so it stays
    out of the rule 35 scope -- which is what makes it safe to add mid-league.
    """
    def row(steps: int) -> artifacts.SubGameOutcome:
        return artifacts.SubGameOutcome(
            sub_game_number=1, roles={"a": "police", "b": "thief"}, started_at="s",
            ended_at="e", result="capture", winner_group="a", github_commit={},
            tokens={}, score={"a": 20, "b": 5}, log_files={}, audit={}, steps=steps)

    ours = artifacts.build_result_artifact("a-vs-b", "u", ["a", "b"], [row(35)], {}, {})
    theirs = artifacts.build_result_artifact("a-vs-b", "u", ["a", "b"], [row(36)], {}, {})
    assert ours["mutual_agreement"]["sha256"] == theirs["mutual_agreement"]["sha256"]
