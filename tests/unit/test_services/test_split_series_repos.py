"""A series lives in two repositories, and its result must not.

Rule 41 puts our cop and our thief in separate repositories. A six-sub-game
series alternates roles, so three logs land in one and three in the other --
and the result builder globbed only its own directory.

On 2026-08-14 that produced two artifacts from one friendly against imreeyal.
Both internally consistent. Both signed. Naming opposite winners:

    best2934-cop   g01,g03,g05   imreeyal 30-15   winner: imreeyal
    best2934-thief g02,g04,g06   best2934 30-15   winner: best2934

The series was a 45-45 tie. Filing either half is the rule-35 contradiction --
two honest teams reporting different winners for a match both played correctly
-- and it is invisible until the halves disagree, which happens on a close
series, at the settlement, when nothing can be done about it.

imreeyal refused to bank a counted series on trust and insisted on a friendly
whose paperwork ran end to end. This is the defect that argument caught.
"""

from __future__ import annotations

import json

import pytest

from p2pchase import constants
from p2pchase.services import network_artifacts

ROLES = {1: constants.ROLE_COP, 2: constants.ROLE_THIEF, 3: constants.ROLE_COP,
         4: constants.ROLE_THIEF, 5: constants.ROLE_COP, 6: constants.ROLE_THIEF}
GAME_ID = "best2934-vs-imreeyal"


def _log(number: int) -> dict:
    """One sub-game log, in the shape the assembler reads off disk.

    Every sub-game survives at the full 35 steps, which is not an arbitrary
    fixture: it is what the six real sub-games did. It also makes the series
    exactly level, so a half-series cannot help but name a winner.
    """
    return {"_filename": f"log_{GAME_ID}_g{number:02d}.json",
            "summary": {"sub_game_number": number, "role": ROLES[number],
                        "result": constants.OUTCOME_SURVIVAL, "tokens_total": 0,
                        "winner_role": None, "started_at": "", "ended_at": "",
                        "audit": {}}}


@pytest.fixture
def two_repos(tmp_path, monkeypatch):
    """A cop repo and a thief repo, each holding its own three sub-games."""
    cop = tmp_path / "best2934-cop" / "artifacts"
    thief = tmp_path / "best2934-thief" / "artifacts"
    for directory in (cop, thief):
        directory.mkdir(parents=True)
    for number in range(1, 7):
        target = cop if ROLES[number] == constants.ROLE_COP else thief
        payload = _log(number)
        (target / payload["_filename"]).write_text(json.dumps(payload), encoding="utf-8")
    return cop, thief


def test_the_result_carries_all_six_sub_games_not_this_repo_s_three(two_repos, peer_config,
                                                                   monkeypatch):
    """The defect, stated as the count that was wrong."""
    cop, thief = two_repos
    monkeypatch.setenv("P2PCHASE_SIBLING_ARTIFACTS", str(thief))
    service = network_artifacts.NetworkArtifactService(peer_config, output_dir=cop)

    numbers = [log["summary"]["sub_game_number"] for log in service.series_logs(GAME_ID)]

    assert numbers == [1, 2, 3, 4, 5, 6], "three of these live in the sibling repository"


def test_a_level_series_settles_as_a_tie_rather_than_a_confident_win(two_repos, peer_config,
                                                                     monkeypatch):
    """The consequence, which is the part that would have cost the match.

    Assembled from one repository the same six sub-games produce a 30-15 win.
    The number is not merely incomplete -- it is confidently wrong, and the
    opponent's report says the opposite with equal confidence.
    """
    cop, thief = two_repos
    monkeypatch.setenv("P2PCHASE_SIBLING_ARTIFACTS", str(thief))
    service = network_artifacts.NetworkArtifactService(peer_config, output_dir=cop)
    path = service.refresh_result(GAME_ID, "uid", "imreeyal")
    final = json.loads(path.read_text(encoding="utf-8"))["final_result"]

    assert final["series_tie"] is True
    assert final["winner_group"] is None
    mine = peer_config.group_id
    assert final["raw_score"] == {mine: 45, "imreeyal": 45}


def test_the_two_repositories_agree_on_the_result(two_repos, peer_config, monkeypatch):
    """Whichever half we assemble from, the answer has to be the same one.

    This is the property that actually matters at settlement: not that some
    directory produces six rows, but that our cop repo and our thief repo
    cannot file contradicting reports about the same series.
    """
    cop, thief = two_repos

    monkeypatch.setenv("P2PCHASE_SIBLING_ARTIFACTS", str(thief))
    ours = json.loads(network_artifacts.NetworkArtifactService(peer_config, output_dir=cop)
                      .refresh_result(GAME_ID, "uid", "imreeyal")
                      .read_text(encoding="utf-8"))
    # Each side points at the *other* one, which is what convention discovery
    # resolves to on a real checkout; the env override only names one path.
    monkeypatch.setenv("P2PCHASE_SIBLING_ARTIFACTS", str(cop))
    theirs = json.loads(network_artifacts.NetworkArtifactService(peer_config, output_dir=thief)
                        .refresh_result(GAME_ID, "uid", "imreeyal")
                        .read_text(encoding="utf-8"))

    assert ours["final_result"] == theirs["final_result"]
    assert ours["mutual_agreement"]["sha256"] == theirs["mutual_agreement"]["sha256"]
    assert ours["mutual_agreement"]["interop_sha256"] == \
        theirs["mutual_agreement"]["interop_sha256"]


def test_a_repository_with_no_sibling_still_assembles_what_it_has(tmp_path, peer_config,
                                                                  monkeypatch):
    """A fresh clone, CI and this suite all have no sibling, and must still work."""
    monkeypatch.setenv("P2PCHASE_SIBLING_ARTIFACTS", str(tmp_path / "nowhere"))
    solo = tmp_path / "artifacts"
    solo.mkdir()
    payload = _log(1)
    (solo / payload["_filename"]).write_text(json.dumps(payload), encoding="utf-8")

    service = network_artifacts.NetworkArtifactService(peer_config, output_dir=solo)

    assert len(service.series_logs(GAME_ID)) == 1
