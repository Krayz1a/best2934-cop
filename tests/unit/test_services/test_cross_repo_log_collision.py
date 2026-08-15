"""Two repositories that both number from g01 must not collapse into one.

`series_logs` merges our cop repo and our thief repo, because rule 41 splits
the roles across two of them and a series needs both halves. It used to key
that merge on ``path.name``.

Against imreeyal the numbering was globally disjoint -- cop 1/3/5, thief 2/4/6
-- so no two files ever shared a name and the merge worked. That was luck.
Against gal-roy1 both repositories numbered from ``g01``, so
``log_best2934-vs-gal-roy1_g01.json`` existed in each and named two different
sub-games. The dict collapsed them: our cop's eight logs overwrote our thief's
first eight, and the result artifact then declared we had played police in all
eight sub-games of a series whose roles must swap. Impossible on its face,
signed anyway, and produced without a single warning.

Found 2026-08-15, while preparing to designate that very series as one of the
two counted games we need to pass. Filing it would have been a rule-35
contradiction voiding the match for gal-roy1 as well as for us.

The key is ``(sub_game_number, role)``: a sub-game is played from exactly one
repository and therefore in exactly one role, so the role is what separates
two files that share a number.
"""

from __future__ import annotations

import json

from p2pchase.services.network_artifacts import NetworkArtifactService


def _log(directory, game_id, sub_game, role, outcome, winner_role):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"log_{game_id}_g{sub_game:02d}.json"
    path.write_text(json.dumps({
        "game_id": game_id,
        "summary": {
            "sub_game_number": sub_game, "role": role, "result": outcome,
            "winner_role": winner_role, "group_id": "best2934",
        },
    }), encoding="utf-8")
    return path


def _service(peer_config, ours, theirs, monkeypatch):
    monkeypatch.setattr(
        "p2pchase.services.network_artifacts.sibling_artifacts_dir",
        lambda counted=False: theirs)
    return NetworkArtifactService(peer_config, ours)


def test_same_number_different_role_are_two_sub_games(peer_config, tmp_path, monkeypatch):
    """The gal-roy1 shape: both repos number from 1, nothing may be dropped."""
    ours, theirs = tmp_path / "cop", tmp_path / "thief"
    game_id = "best2934-vs-gal-roy1"
    for n in (1, 2, 3):
        _log(ours, game_id, n, "police", "capture", "police")
        _log(theirs, game_id, n, "thief", "survival", "thief")

    logs = _service(peer_config, ours, theirs, monkeypatch).series_logs(game_id)

    assert len(logs) == 6
    roles = [row["summary"]["role"] for row in logs]
    assert roles.count("police") == 3
    assert roles.count("thief") == 3


def test_a_series_whose_roles_never_swap_cannot_be_assembled(peer_config, tmp_path,
                                                             monkeypatch):
    """The symptom that exposed the bug, asserted as the thing that must not recur.

    A result naming us police in every sub-game is impossible: the roles have
    to swap. Before the fix that is exactly what came out.
    """
    ours, theirs = tmp_path / "cop", tmp_path / "thief"
    game_id = "best2934-vs-gal-roy1"
    for n in range(1, 9):
        _log(ours, game_id, n, "police", "capture", "police")
    for n in range(1, 9):
        _log(theirs, game_id, n, "thief", "survival", "thief")

    logs = _service(peer_config, ours, theirs, monkeypatch).series_logs(game_id)

    assert {row["summary"]["role"] for row in logs} == {"police", "thief"}
    assert len(logs) == 16


def test_the_imreeyal_shape_still_merges_as_it_did(peer_config, tmp_path, monkeypatch):
    """Disjoint numbering was already correct and must stay byte-for-byte so."""
    ours, theirs = tmp_path / "cop", tmp_path / "thief"
    game_id = "best2934-vs-imreeyal"
    for n in (1, 3, 5):
        _log(ours, game_id, n, "police", "capture", "police")
    for n in (2, 4, 6):
        _log(theirs, game_id, n, "thief", "survival", "thief")

    logs = _service(peer_config, ours, theirs, monkeypatch).series_logs(game_id)

    assert [row["summary"]["sub_game_number"] for row in logs] == [1, 2, 3, 4, 5, 6]


def test_a_true_duplicate_still_prefers_our_own_copy(peer_config, tmp_path, monkeypatch):
    """Same number AND same role is a stale or hand-copied file, not a sub-game.

    Our own directory wins, so the outcome stays deterministic and explicable.
    A real one of these existed: a 2026-08-09 police log sitting in the thief
    repo, five days older than the series it was being folded into.
    """
    ours, theirs = tmp_path / "cop", tmp_path / "thief"
    game_id = "best2934-vs-gal-roy1"
    _log(theirs, game_id, 6, "police", "survival", "thief")   # stale
    _log(ours, game_id, 6, "police", "capture", "police")     # real

    logs = _service(peer_config, ours, theirs, monkeypatch).series_logs(game_id)

    assert len(logs) == 1
    assert logs[0]["summary"]["result"] == "capture"


def test_order_is_stable_and_grouped_by_sub_game_number(peer_config, tmp_path, monkeypatch):
    ours, theirs = tmp_path / "cop", tmp_path / "thief"
    game_id = "best2934-vs-gal-roy1"
    for n in (1, 2):
        _log(ours, game_id, n, "police", "capture", "police")
        _log(theirs, game_id, n, "thief", "survival", "thief")

    logs = _service(peer_config, ours, theirs, monkeypatch).series_logs(game_id)

    assert [(r["summary"]["sub_game_number"], r["summary"]["role"]) for r in logs] == [
        (1, "police"), (1, "thief"), (2, "police"), (2, "thief")]
