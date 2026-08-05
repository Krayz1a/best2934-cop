"""The four mandatory JSON artifacts (book ch9.3.3, Appendix F Table 20)."""

from __future__ import annotations

import json

from p2pchase.reports import artifacts


def identity(group: str = "test1234") -> artifacts.GroupIdentity:
    return artifacts.GroupIdentity(
        group_id=group, group_name=group, members=["A Tester"],
        repos={"cop": "https://example.invalid/cop"},
        mcp_servers={"url": "http://127.0.0.1:9901/mcp"},
        llm_model="template", hardware_spec={"cpu_type": "test"},
    )


def test_the_game_id_is_the_same_from_either_side():
    """Both peers must derive the same name without exchanging it."""
    assert artifacts.make_game_id("b", "a") == artifacts.make_game_id("a", "b") == "a-vs-b"


def test_uids_are_unique():
    assert len({artifacts.new_game_uid() for _ in range(50)}) == 50


def test_timestamps_carry_an_explicit_offset():
    assert "+" in artifacts.now_iso() or artifacts.now_iso().endswith("Z")


def test_filenames_are_derived_from_the_game_id(tmp_path):
    names = artifacts.ArtifactSet("a-vs-b", tmp_path)
    assert names.declaration().name == "declaration_a-vs-b.json"
    assert names.config(3).name == "config_a-vs-b_g03.json"
    assert names.log(12).name == "log_a-vs-b_g12.json"
    assert names.result().name == "result_a-vs-b.json"


def test_the_expected_file_set_is_enumerable(tmp_path):
    paths = artifacts.ArtifactSet("a-vs-b", tmp_path).all_paths(sub_games=6)
    assert len(paths) == 14  # declaration + result + 6 configs + 6 logs


def test_an_identity_signs_itself():
    body = identity().as_dict()
    assert len(body["signature"]) == 64
    changed = identity()
    changed.members = ["Someone Else"]
    assert changed.as_dict()["signature"] != body["signature"]


def test_a_supplied_signature_is_preserved():
    fixed = identity()
    fixed.signature = "x" * 64
    assert fixed.as_dict()["signature"] == "x" * 64


def test_the_declaration_carries_no_role_or_sub_game():
    """Roles swap between sub-games, so neither belongs in the series spine."""
    body = artifacts.build_declaration("a-vs-b", "uid", identity("a"), identity("b"))
    assert "role" not in json.dumps(body["groups"])
    assert "sub_game_number" not in body
    assert body["groups"]["group_1"]["group_id"] == "a"


def test_the_config_artifact_locks_the_agreed_terms(shared_config):
    body = artifacts.build_config_artifact(shared_config, "a-vs-b", "uid", 1, ["b", "a"])
    assert body["config_sha256"] == artifacts.digest_payload(shared_config)
    assert body["agreed_between"] == ["a", "b"]
    assert body["config_name"] == "config_a-vs-b_g01.json"


def test_the_config_digest_ignores_derived_naming(shared_config):
    """Naming metadata is identical on both sides by construction, so it is excluded."""
    first = artifacts.build_config_artifact(shared_config, "a-vs-b", "uid1", 1, ["a", "b"])
    second = artifacts.build_config_artifact(shared_config, "a-vs-b", "uid2", 5, ["a", "b"])
    assert first["config_sha256"] == second["config_sha256"]


def test_the_log_counts_steps_excluding_the_step_zero_declaration():
    records = [{"payload": {"step": n}} for n in range(4)]
    body = artifacts.build_log_artifact(
        "a-vs-b", "uid", 1, "a", "police", "b", "survival", "thief", records,
        "2026-08-01T10:00:00+00:00", "2026-08-01T10:02:30+00:00", 0, {"passed": True},
    )
    assert body["summary"]["steps"] == 3
    assert body["summary"]["duration_seconds"] == 150.0
    assert body["mutual_agreement"]["confirmed"] is False


def test_a_broken_timestamp_does_not_destroy_a_sound_log():
    body = artifacts.build_log_artifact(
        "a-vs-b", "uid", 1, "a", "police", "b", "survival", None, [],
        "not-a-date", "also-not", 0, {"passed": True},
    )
    assert body["summary"]["duration_seconds"] == 0.0


def outcome(number: int = 1) -> artifacts.SubGameOutcome:
    return artifacts.SubGameOutcome(
        sub_game_number=number, roles={"a": "police", "b": "thief"},
        started_at="s", ended_at="e", result="capture", winner_group="a",
        github_commit={"a": "abc123"}, tokens={"a": 0, "b": 0},
        score={"a": 20, "b": 5}, log_files={"a": "log.json"}, audit={"passed": True},
    )


def test_the_result_carries_an_agreement_digest():
    body = artifacts.build_result_artifact(
        "a-vs-b", "uid", ["b", "a"], [outcome()], {"winner_group": "a"}, {"a": 0, "b": 0})
    assert len(body["mutual_agreement"]["sha256"]) == 64
    assert body["mutual_agreement"]["confirmed"] is False
    assert body["groups"] == ["a", "b"]
    assert body["num_sub_games"] == 1


def test_a_different_match_produces_a_different_digest():
    """Rule 35: a contradiction must be provable, not arguable.

    The contradiction has to be about the *match*. This used to vary the
    ``final_result`` dict each side passes in, which no longer moves the digest
    -- totals are now recomputed from the sub-games so that both peers derive
    the hashed number from the same six facts rather than each trusting its own
    aggregator. So the disagreement is expressed where a real one lives: in who
    won a sub-game.
    """
    theirs = outcome()
    theirs.winner_group = "b"
    ours = artifacts.build_result_artifact(
        "a-vs-b", "uid", ["a", "b"], [outcome()], {}, {})
    contradicting = artifacts.build_result_artifact(
        "a-vs-b", "uid", ["a", "b"], [theirs], {}, {})
    assert ours["mutual_agreement"]["sha256"] != contradicting["mutual_agreement"]["sha256"]


def test_our_own_scoring_engine_agrees_with_the_hashed_totals():
    """The gap that recomputing totals opens, closed.

    The digest covers totals derived from the sub-games; the report body still
    carries our scoring engine's own figures. If those two ever disagree we
    would file a report whose text contradicts its own digest -- which is the
    rule 35 void, self-inflicted and against nobody.
    """
    from p2pchase.domain.scoring import ScoreTable, SeriesTally
    from p2pchase.reports.agreed import agreed_summary

    won = outcome()  # a capture: cop "a" takes 20, thief "b" takes 5
    tally = SeriesTally(group_a="a", group_b="b")
    tally.record(won.roles, won.result, ScoreTable())

    derived = agreed_summary("a-vs-b", ["a", "b"], [won], with_totals=True)["totals"]
    engine = tally.finalise()
    assert derived["scores"] == engine["raw_score"]
    assert derived["total_score"] == engine["total_score"]
    assert derived["sub_games_won"] == engine["sub_games_won"]
    assert derived["series_tie"] == engine["series_tie"]
    assert derived["winner"] == engine["winner_group"]


def test_writing_creates_parents_and_valid_json(tmp_path):
    path = artifacts.write_json(tmp_path / "deep" / "x.json", {"k": "ש"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"k": "ש"}
