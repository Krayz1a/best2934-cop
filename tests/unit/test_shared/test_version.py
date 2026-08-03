"""Version tracking and compatibility refusal (guidelines §8.1)."""

from __future__ import annotations

import json

import pytest

from p2pchase.shared.paths import artifacts_dir, config_dir, ensure, project_root
from p2pchase.shared.rate_limits import (
    DEFAULT_RATE_LIMITS,
    RateLimitError,
    load_rate_limits,
    service_limits,
    validate_rate_limits,
)
from p2pchase.shared.version import (
    CODE_VERSION,
    CONFIG_VERSION,
    VersionMismatchError,
    is_compatible,
    validate_config_version,
)


def test_versions_start_at_one():
    assert CODE_VERSION == "1.00"
    assert CONFIG_VERSION == "1.00"


def test_a_newer_minor_is_still_readable():
    """A minor bump only adds optional keys, so an older reader copes."""
    assert is_compatible("1.05", "1.00")
    assert is_compatible("1.00", "1.99")


def test_a_major_bump_is_not_readable():
    assert not is_compatible("2.00", "1.00")


def test_a_malformed_version_is_refused():
    with pytest.raises(VersionMismatchError, match="malformed"):
        is_compatible("banana", "1.00")


def test_a_missing_version_key_is_refused():
    with pytest.raises(VersionMismatchError, match="no 'version' key"):
        validate_config_version(None)


def test_an_incompatible_config_refuses_to_load():
    with pytest.raises(VersionMismatchError, match="Refusing to run"):
        validate_config_version("2.00", "1.00", "game.json")


def test_a_compatible_config_passes_silently():
    assert validate_config_version("1.00") is None


def test_service_limits_fall_back_through_default_then_book():
    limits = service_limits(DEFAULT_RATE_LIMITS, "unknown-service")
    assert limits["requests_per_minute"] == 30
    assert limits["queue_depth"] == 100


def test_service_limits_prefer_the_named_service():
    config = {"services": {"default": {"requests_per_minute": 30},
                           "gmail": {"requests_per_minute": 45}}}
    assert service_limits(config, "gmail")["requests_per_minute"] == 45


def test_the_shipped_rate_limits_are_legal():
    assert validate_rate_limits(DEFAULT_RATE_LIMITS) == []


def test_throttling_below_the_book_floor_is_reported():
    """Table 19 values are minimums: raise them freely, never lower them."""
    problems = validate_rate_limits({"services": {"gmail": {"requests_per_minute": 5}}})
    assert len(problems) == 1
    assert "never lowered" in problems[0]


def test_a_rate_limit_file_loads(tmp_path):
    path = tmp_path / "rate_limits.json"
    path.write_text(json.dumps(DEFAULT_RATE_LIMITS), encoding="utf-8")
    assert load_rate_limits(path)["version"] == "1.00"


def test_a_malformed_rate_limit_file_is_a_config_failure(tmp_path):
    path = tmp_path / "rate_limits.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(RateLimitError, match="not valid JSON"):
        load_rate_limits(path)


def test_an_illegal_rate_limit_file_refuses_to_load(tmp_path):
    path = tmp_path / "rate_limits.json"
    path.write_text(json.dumps({"version": "1.00",
                                "services": {"gmail": {"max_retries": 0}}}),
                    encoding="utf-8")
    with pytest.raises(RateLimitError, match="below Appendix F"):
        load_rate_limits(path)


def test_paths_are_derived_never_hard_coded(repo_root, tmp_path, monkeypatch):
    assert project_root() == repo_root
    assert config_dir().name == "config"
    assert artifacts_dir().parent == repo_root
    monkeypatch.setenv("P2PCHASE_ROOT", str(tmp_path))
    assert project_root() == tmp_path


def test_ensure_creates_and_returns(tmp_path):
    target = ensure(tmp_path / "a" / "b")
    assert target.is_dir()
