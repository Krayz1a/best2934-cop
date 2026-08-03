"""Shared fixtures (guidelines §6.1 rule 4).

Everything here is cheap and deterministic. No test touches the network, the
filesystem outside ``tmp_path``, or a real API -- guidelines §6.1 rule 7 is
explicit that tests must not depend on external services, and a test suite that
needs a running opponent is a test suite nobody runs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2pchase.domain.board import Board, BoardGeometry, build_board
from p2pchase.domain.own_state import build_own_state
from p2pchase.shared.config import load_config
from p2pchase.shared.config_schema import DEFAULT_SHARED, deep_merge
from p2pchase.shared.peer_config import PeerConfig

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def shared_config() -> dict:
    """The Appendix F defaults, as a plain dict."""
    return deep_merge({}, DEFAULT_SHARED)


@pytest.fixture
def geometry() -> BoardGeometry:
    return BoardGeometry(grid_size=7)


@pytest.fixture
def board(shared_config) -> Board:
    return build_board(shared_config)


@pytest.fixture
def cop_state(shared_config, board):
    return build_own_state(shared_config, "police", board)


@pytest.fixture
def thief_state(shared_config):
    return build_own_state(shared_config, "thief", build_board(shared_config))


@pytest.fixture
def setup_payload() -> dict:
    """A minimal private setup file, with no secrets in it."""
    return {
        "version": "1.00",
        "game": {
            "group_id": "test1234",
            "group_name": "test1234",
            "members": ["A Tester"],
            "repos": {"cop": "https://example.invalid/cop"},
        },
        "network": {"my_port": 9901, "opponent_url": "http://127.0.0.1:9902/mcp"},
        "strategy": {},
        "trash_talk": {"provider": "template", "seed": 1},
        "llm": {},
        "email": {"enabled": False},
    }


@pytest.fixture
def peer_config(shared_config, setup_payload) -> PeerConfig:
    """A ready-to-use config that never reads a file."""
    return PeerConfig(role="police", shared=shared_config, setup=setup_payload)


@pytest.fixture
def thief_config(shared_config, setup_payload) -> PeerConfig:
    thief_setup = dict(setup_payload)
    thief_setup["game"] = dict(setup_payload["game"], group_id="rival999")
    return PeerConfig(role="thief", shared=shared_config, setup=thief_setup)


@pytest.fixture
def config_dir(tmp_path, shared_config, setup_payload) -> Path:
    """A throwaway config directory on disk, for loader tests."""
    (tmp_path / "game.json").write_text(json.dumps(shared_config), encoding="utf-8")
    (tmp_path / "setup.json").write_text(json.dumps(setup_payload), encoding="utf-8")
    return tmp_path


@pytest.fixture
def loaded_config(config_dir) -> PeerConfig:
    return load_config(config_dir, "police")


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT
