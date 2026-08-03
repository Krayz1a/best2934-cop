"""A full local series, and the four artifacts it must produce.

Appendix C makes the artifact set a submission requirement, not a convenience:
one declaration, one config and one log per sub-game, and one result. This test
plays a real series through the SDK -- the only entry point any consumer is
allowed to use -- and then checks the files on disk the way a grader would:
by opening them.

Every path here writes into ``tmp_path``, so running the suite never touches
the repository's own ``artifacts/`` directory.
"""

from __future__ import annotations

import json

import pytest

from p2pchase import constants
from p2pchase.sdk.sdk import P2PChaseSDK
from p2pchase.services.match_service import roles_for_sub_game

OPPONENT = "rival999"


@pytest.fixture
def sdk(peer_config, tmp_path) -> P2PChaseSDK:
    return P2PChaseSDK(peer_config, output_dir=tmp_path, signing_secret="test-secret")


@pytest.fixture
def series(sdk):
    return sdk.run_series(OPPONENT, sub_games=2, seed=3)


def test_the_roles_swap_between_sub_games(peer_config):
    """Rule 12: neither team may keep the easier half of the asymmetry."""
    first = roles_for_sub_game(1, "us", "them")
    second = roles_for_sub_game(2, "us", "them")
    assert first["us"] == constants.ROLE_COP
    assert second["us"] == constants.ROLE_THIEF
    assert first["them"] != second["them"]


def test_a_series_writes_every_mandatory_artifact(series, tmp_path):
    written = {path.name for path in series.paths}
    assert any(name.startswith("declaration_") for name in written)
    assert sum(name.startswith("config_") for name in written) == 2
    assert sum(name.startswith("log_") for name in written) == 2
    assert any(name.startswith("result_") for name in written)
    assert all(path.exists() for path in series.paths)


def test_every_artifact_is_valid_json_naming_its_game(series):
    for path in series.paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["game_id"] == series.game_id
        assert payload["game_uid"] == series.game_uid


def test_each_sub_game_produced_a_decided_outcome(series):
    assert len(series.outcomes) == 2
    for outcome in series.outcomes:
        assert outcome.result in (constants.OUTCOME_CAPTURE, constants.OUTCOME_SURVIVAL)
        assert outcome.audit["passed"] is True


def test_the_series_tally_covers_both_teams(series, peer_config):
    total = series.final_result["total_score"]
    assert set(total) == {peer_config.group_id, OPPONENT}


def test_every_written_log_verifies_through_the_sdk(series, sdk):
    """Our own logs must pass the same audit we will subject the opponent to."""
    logs = [p for p in series.paths if p.name.startswith("log_")]
    assert logs
    for verdict in sdk.verification.verify_own(logs):
        assert verdict.passed, verdict.banner
        assert verdict.failed_steps == []


def test_step_zero_is_committed_and_verifies_with_the_rest(series, sdk):
    """Rule 24's declaration is sealed like any other step, not pasted in raw.

    This is asserted explicitly because writing it raw is an easy mistake that
    breaks every log at step 0 while leaving the rest of the chain intact.
    """
    log = next(p for p in series.paths if p.name.startswith("log_"))
    payload = json.loads(log.read_text(encoding="utf-8"))
    first = payload["records"][0]
    assert first["commit"], "step 0 carries no commitment"
    assert first["payload"]["step"] == 0
    assert first["payload"]["type"] == "system_spec"
    # Signed proves we declared it; committed proves we declared it beforehand.
    assert first["payload"]["signature"]
    assert first["payload"]["spec"]["cpu_cores"] >= 1


def test_a_tampered_log_file_is_caught_on_replay(series, sdk):
    """The grader's own check, run against a deliberately corrupted file."""
    log = next(p for p in series.paths if p.name.startswith("log_"))
    payload = json.loads(log.read_text(encoding="utf-8"))
    payload["records"][2]["payload"]["move"] = "STAY"
    log.write_text(json.dumps(payload), encoding="utf-8")

    verdict = sdk.verify_log(log)
    assert verdict.passed is False
    assert verdict.failed_steps
    assert "INTEGRITY FAILURE" in verdict.banner


def test_the_replay_report_renders_something_a_human_can_read(series, sdk):
    log = next(p for p in series.paths if p.name.startswith("log_"))
    text = sdk.replay_text(log, limit=5)
    assert "Verified OK" in text
    assert series.game_id in text


def test_both_teams_computing_the_same_result_agree(series, sdk):
    """Rule 35: matching digests are what stands in for a referee's word."""
    digest = sdk.verification.agreement_digest(series.final_result)
    assert sdk.verification.confirm_agreement(series.final_result, digest)
    assert not sdk.verification.confirm_agreement(series.final_result, "0" * 64)
