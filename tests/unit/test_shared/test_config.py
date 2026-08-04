"""Config loading, and refusing to play an illegal match (book Appendix B, F)."""

from __future__ import annotations

import json

import pytest

from p2pchase import constants
from p2pchase.shared.config import ConfigError, load_config
from p2pchase.shared.config_schema import deep_merge, dig, validate_shared


def test_dig_walks_a_dotted_path(shared_config):
    assert dig(shared_config, "board_and_agents.grid_size") == 7
    assert dig(shared_config, "board_and_agents.nope") is None
    assert dig(shared_config, "nope.nope") is None


def test_deep_merge_lets_the_overlay_win():
    merged = deep_merge({"a": {"x": 1, "y": 2}}, {"a": {"y": 9}})
    assert merged == {"a": {"x": 1, "y": 9}}


def test_the_shipped_defaults_are_legal(shared_config):
    assert validate_shared(shared_config) == []


def test_changing_a_permanent_parameter_is_reported(shared_config):
    """Appendix F: deviation on a permanent term disqualifies the team."""
    illegal = deep_merge(shared_config, {"scoring": {"capture_cop": 999}})
    problems = validate_shared(illegal)
    assert len(problems) == 1
    assert "PERMANENT" in problems[0]
    assert "capture_cop" in problems[0]


def test_lowering_a_minimum_is_reported(shared_config):
    illegal = deep_merge(shared_config, {"board_and_agents": {"grid_size": 5}})
    problems = validate_shared(illegal)
    assert "MINIMUM" in problems[0]
    assert "never lowered" in problems[0]


def test_raising_a_minimum_is_allowed(shared_config):
    legal = deep_merge(shared_config, {"board_and_agents": {"grid_size": 11}})
    assert validate_shared(legal) == []


def test_every_problem_is_reported_at_once(shared_config):
    """One round trip should tell a negotiating team the whole story."""
    illegal = deep_merge(shared_config, {
        "scoring": {"capture_cop": 999, "tie_score": 7},
        "movement_and_barriers": {"max_moves": 3},
    })
    assert len(validate_shared(illegal)) == 3


def test_a_config_directory_loads(config_dir):
    config = load_config(config_dir, "police")
    assert config.group_id == "test1234"
    assert config.my_port == 9901
    assert config.problems == []


def test_a_missing_setup_file_is_a_clear_failure(tmp_path):
    with pytest.raises(ConfigError, match="missing private setup file"):
        load_config(tmp_path, "police")


def test_malformed_json_is_a_config_failure_not_a_crash(tmp_path):
    (tmp_path / "setup.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigError, match="not valid JSON"):
        load_config(tmp_path, "police")


def test_a_json_array_is_refused(tmp_path):
    (tmp_path / "setup.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ConfigError, match="must contain a JSON object"):
        load_config(tmp_path, "police")


def test_an_illegal_shared_config_refuses_to_start(tmp_path, shared_config, setup_payload):
    """Better to fail loudly than to quietly play a match that cannot count."""
    illegal = deep_merge(shared_config, {"pheromones": {"pheromone_decay": 0.5}})
    (tmp_path / "game.json").write_text(json.dumps(illegal), encoding="utf-8")
    (tmp_path / "setup.json").write_text(json.dumps(setup_payload), encoding="utf-8")
    with pytest.raises(ConfigError, match="violates Appendix F"):
        load_config(tmp_path, "police")


def test_lenient_mode_reports_instead_of_raising(tmp_path, shared_config, setup_payload):
    """Negotiation must be able to inspect a config it would refuse to play."""
    illegal = deep_merge(shared_config, {"pheromones": {"pheromone_decay": 0.5}})
    (tmp_path / "game.json").write_text(json.dumps(illegal), encoding="utf-8")
    (tmp_path / "setup.json").write_text(json.dumps(setup_payload), encoding="utf-8")
    config = load_config(tmp_path, "police", strict=False)
    assert config.problems


def test_the_reporting_address_cannot_be_redirected(loaded_config):
    """A team must not be able to opt out of reporting by editing a file."""
    loaded_config.setup["email"]["recipient"] = "attacker@example.invalid"
    assert loaded_config.email["recipient"] == constants.AGENT_REPORT_EMAIL


def test_the_config_digest_covers_the_agreed_terms_only(loaded_config):
    before = loaded_config.config_sha256()
    loaded_config.setup["network"]["my_port"] = 12345
    assert loaded_config.config_sha256() == before  # private settings are not signed
    loaded_config.shared["world"]["hint_max_words"] = 20
    assert loaded_config.config_sha256() != before


def test_the_canonical_form_is_stable(loaded_config):
    assert loaded_config.canonical_shared() == loaded_config.canonical_shared()


def test_repository_config_is_legal(repo_root):
    """The configs we actually ship must pass the same gate."""
    for role in ("police", "thief"):
        config = load_config(repo_root / "config" / role, role)
        assert config.problems == []


def test_the_shipped_role_is_a_single_constant(repo_root):
    """`best2934-cop` and `best2934-thief` differ by one line, not two codebases.

    Both roles are fully implemented here and either can be selected with
    ``--role``. ``DEFAULT_ROLE`` is what the sibling repository flips, so it has
    to be a real role and it has to be what an argument-free load picks up --
    otherwise the two repositories would silently play the same side.
    """
    assert constants.DEFAULT_ROLE in (constants.ROLE_COP, constants.ROLE_THIEF)
    default = load_config(repo_root / "config" / constants.DEFAULT_ROLE)
    assert default.role == constants.DEFAULT_ROLE
