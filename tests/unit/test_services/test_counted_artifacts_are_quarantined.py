"""A counted series may never be assembled from friendly logs, or vice versa.

``refresh_result`` rebuilds the series from every ``log_<game_id>_g*.json`` on
disk across both repositories, after every sub-game. Rule 52 allows one counted
game per opponent, so a counted series against a team we have played friendlies
with **reuses the same game_id** -- it must, because ``game_id`` is the first
key of the ``interop_sha256`` scope and has to match the opponent byte for
byte. So without separation, sub-game 1 of a counted run is assembled against
sub-games 2-6 of the friendly and signed as a series: internally consistent, a
report of a match that never happened, and a rule-35 void for *both* teams.

On 2026-08-14 this was avoided by hand, nine minutes before a series started.
These tests are the control that replaces the memory.
"""

from __future__ import annotations

import json

import pytest

from p2pchase.shared.paths import COUNTED_SUBDIR, artifacts_dir


def _log(directory, game_id, sub_game, winner):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"log_{game_id}_g{sub_game:02d}.json"
    path.write_text(json.dumps({
        "game_id": game_id, "sub_game_number": sub_game,
        "summary": {"winner_group": winner, "result": "capture"},
    }), encoding="utf-8")
    return path


def test_counted_directory_is_below_the_friendly_one():
    assert artifacts_dir(counted=True) == artifacts_dir() / COUNTED_SUBDIR


def test_friendly_is_the_default_so_a_forgotten_flag_never_writes_counted():
    """Absent means friendly. The dangerous default is the other way round."""
    assert artifacts_dir() == artifacts_dir(counted=False)
    assert COUNTED_SUBDIR not in artifacts_dir().parts[-1:]


@pytest.mark.parametrize("counted", [False, True])
def test_service_directory_follows_the_counted_flag(peer_config, tmp_path, counted):
    from p2pchase.services.network_artifacts import NetworkArtifactService

    service = NetworkArtifactService(peer_config, tmp_path, counted=counted)
    assert service.counted is counted


def test_for_opponent_reads_counted_from_the_pairing(peer_config, tmp_path):
    """The flag comes from config, so a caller cannot forget to pass it."""
    from p2pchase.services.network_artifacts import NetworkArtifactService

    service = NetworkArtifactService.for_opponent(peer_config, "imreeyal", tmp_path)
    expected, _ = peer_config.counted_series("imreeyal")
    assert service.counted is bool(expected)


def _isolate_sibling(monkeypatch, tmp_path):
    """Point the sibling lookup at the sandbox, not at the real other repo.

    Without this these tests read the developer's actual thief/cop repository.
    Both passed anyway until 2026-08-15, because `series_logs` keyed its merge
    on the filename and the real sibling's logs happened to share names with
    the fixture's -- so the leak was silently overwritten. The moment that key
    was corrected the leak surfaced as three extra sub-games. A test that
    depends on what is lying in another directory is not a test.
    """
    monkeypatch.setattr(
        "p2pchase.services.network_artifacts.sibling_artifacts_dir",
        lambda counted=False: tmp_path / "sibling" / (COUNTED_SUBDIR if counted else ""))


def test_a_counted_assembly_cannot_see_friendly_logs(peer_config, tmp_path, monkeypatch):
    """The whole point: same game_id, two statuses, no mixing.

    Six friendly logs and one counted log share a game id. The counted
    assembly must find exactly the one, never seven.
    """
    from p2pchase.services.network_artifacts import NetworkArtifactService

    _isolate_sibling(monkeypatch, tmp_path)
    game_id = "best2934-vs-imreeyal"
    for n in range(1, 7):
        _log(tmp_path, game_id, n, "imreeyal")
    _log(tmp_path / COUNTED_SUBDIR, game_id, 1, "best2934")

    counted = NetworkArtifactService(peer_config, tmp_path / COUNTED_SUBDIR, counted=True)
    found = counted.series_logs(game_id)
    assert len(found) == 1
    assert found[0]["summary"]["winner_group"] == "best2934"


def test_a_friendly_assembly_cannot_see_counted_logs(peer_config, tmp_path, monkeypatch):
    """And the other direction, which is the one that silently inflates a friendly."""
    from p2pchase.services.network_artifacts import NetworkArtifactService

    _isolate_sibling(monkeypatch, tmp_path)
    game_id = "best2934-vs-imreeyal"
    for n in range(1, 7):
        _log(tmp_path, game_id, n, "imreeyal")
    _log(tmp_path / COUNTED_SUBDIR, game_id, 1, "best2934")

    friendly = NetworkArtifactService(peer_config, tmp_path, counted=False)
    found = friendly.series_logs(game_id)
    assert len(found) == 6
    assert {row["summary"]["winner_group"] for row in found} == {"imreeyal"}
