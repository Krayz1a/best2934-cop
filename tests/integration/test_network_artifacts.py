"""A live sub-game must leave the same four artifacts a rehearsal does.

Until this existed, ``p2pchase play`` printed its outcome and wrote nothing. A
match with no log cannot be replayed by the opponent (rule 20), cannot be
mutually audited (rule 36) and cannot be reported (rules 32-35) -- three
separate disqualifications from a path that looked like it worked, because the
thing it failed to do left no trace.

These tests therefore assert about files on disk, not about return values.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from p2pchase import constants
from p2pchase.mcp.client import LoopbackClient
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.reports.naming import now_iso
from p2pchase.runtime.peer import PeerRunner
from p2pchase.runtime.peer_session import PeerSession
from p2pchase.sdk import P2PChaseSDK

GAME_ID = "best2934_vs_rival999"


@pytest.fixture
def live_sub_game(peer_config, thief_config, tmp_path):
    """Play one sub-game over the protocol and record it as the CLI would."""
    cop = PeerSession(config=peer_config, role=constants.ROLE_COP, game_id=GAME_ID, seed=5)
    thief = PeerSession(config=thief_config, role=constants.ROLE_THIEF, game_id=GAME_ID, seed=6)
    cop_runner = PeerRunner(peer_config, cop, LoopbackClient(PeerHandlers(thief_config, thief)))
    thief_runner = PeerRunner(thief_config, thief, LoopbackClient(PeerHandlers(peer_config, cop)))

    started = now_iso()

    async def drive():
        return await asyncio.gather(cop_runner.run_sub_game(), thief_runner.run_sub_game())

    cop_outcome, _ = asyncio.run(drive())

    sdk = P2PChaseSDK(peer_config, output_dir=tmp_path)
    handshake = {"group_id": thief_config.group_id, "group_name": "rival999",
                 "repos": {"cop": "https://example.invalid/their-cop",
                           "thief": "https://example.invalid/their-thief"}}
    paths = sdk.record_networked_sub_game(GAME_ID, 1, thief_config.group_id, cop_outcome,
                                          started, now_iso(), cop.talk.tokens_used, handshake)
    return sdk, cop_outcome, paths, tmp_path


def test_a_live_sub_game_writes_all_four_artifacts(live_sub_game):
    _, _, paths, tmp_path = live_sub_game
    names = sorted(path.name for path in paths)
    assert names == [f"config_{GAME_ID}_g01.json", f"declaration_{GAME_ID}.json",
                     f"log_{GAME_ID}_g01.json", f"result_{GAME_ID}.json"]
    for path in paths:
        assert json.loads(path.read_text(encoding="utf-8"))  # all valid JSON


def test_the_log_is_verifiable_by_the_opponent(live_sub_game):
    """The point of writing it: someone else can check the chain unaided."""
    sdk, outcome, paths, _ = live_sub_game
    log = next(path for path in paths if path.name.startswith("log_"))
    verdict = sdk.verify_log(log)
    assert verdict.passed
    assert verdict.verified_steps == outcome.steps + 1  # step 0 is the declaration


def test_step_zero_is_the_first_record(live_sub_game):
    """Rule 24: the hardware declaration is committed *before* the first move."""
    _, _, paths, _ = live_sub_game
    log = json.loads(next(p for p in paths if p.name.startswith("log_")).read_text())
    assert log["records"][0]["payload"]["type"] == "system_spec"
    assert log["summary"]["steps"] == len(log["records"]) - 1


def test_the_result_carries_four_repository_links(live_sub_game):
    """Rule 49: both teams' cop and thief repositories, inside the JSON."""
    _, _, paths, _ = live_sub_game
    result = json.loads(next(p for p in paths if p.name.startswith("result_")).read_text())
    repos = result["repositories"]
    assert set(repos) == {"test1234", "rival999"}
    assert repos["rival999"]["thief"] == "https://example.invalid/their-thief"
    assert repos["test1234"]["cop"] == "https://example.invalid/cop"


def test_a_second_sub_game_extends_the_same_result(live_sub_game, peer_config, thief_config):
    """One game_uid, two sub-games -- not two games with one sub-game each."""
    sdk, outcome, paths, tmp_path = live_sub_game
    first = json.loads(next(p for p in paths if p.name.startswith("result_")).read_text())

    sdk.record_networked_sub_game(GAME_ID, 2, thief_config.group_id, outcome,
                                  now_iso(), now_iso(), 0, {})
    result_path = next(p for p in paths if p.name.startswith("result_"))
    second = json.loads(result_path.read_text(encoding="utf-8"))

    assert second["game_uid"] == first["game_uid"]
    assert second["num_sub_games"] == 2
    assert [entry["sub_game_number"] for entry in second["sub_games"]] == [1, 2]


def test_the_series_result_scores_both_teams(live_sub_game):
    _, _, paths, _ = live_sub_game
    result = json.loads(next(p for p in paths if p.name.startswith("result_")).read_text())
    totals = result["final_result"]["total_score"]
    assert set(totals) == {"test1234", "rival999"}
    assert all(isinstance(points, int) for points in totals.values())


def test_the_commit_hash_that_played_is_recorded(live_sub_game):
    """Rule 53: the code may change between sub-games, so each one names its commit."""
    _, _, paths, _ = live_sub_game
    result = json.loads(next(p for p in paths if p.name.startswith("result_")).read_text())
    assert "test1234" in result["sub_games"][0]["github_commit"]


class _StubBrain:
    """A brain that always does the same thing, so a test can force a collision."""

    def __init__(self, move: str = "STAY") -> None:
        self.move = move

    def decide(self, _state):
        from p2pchase.domain.brains import Decision
        return Decision(move=self.move, rationale="stub")


def _adjacent_config(config, cop, thief):
    """A copy of the shared config with the two agents placed where we want them."""
    import copy
    clone = copy.deepcopy(config)
    clone.shared["board_and_agents"]["cop_start"] = list(cop)
    clone.shared["board_and_agents"]["thief_start"] = list(thief)
    return clone


def test_a_capture_ends_a_networked_sub_game(peer_config, thief_config):
    """Rules 21, 22: the cop claims, the thief answers, and the game stops.

    Before this existed the networked path checked only for survival, so a cop
    standing on the thief in a real league match would have played on to the
    move ceiling and scored the sub-game as the thief's. The bug was invisible
    locally, because the local harness compares both positions directly -- a
    luxury no peer has.
    """
    cop_config = _adjacent_config(peer_config, (3, 2), (3, 3))
    thief_side = _adjacent_config(thief_config, (3, 2), (3, 3))

    cop = PeerSession(config=cop_config, role=constants.ROLE_COP, game_id=GAME_ID, seed=1)
    thief = PeerSession(config=thief_side, role=constants.ROLE_THIEF, game_id=GAME_ID, seed=2)
    cop.brain = _StubBrain("E")     # steps onto the thief's cell
    thief.brain = _StubBrain("STAY")  # and the thief does not move away

    cop_runner = PeerRunner(cop_config, cop, LoopbackClient(PeerHandlers(thief_side, thief)))
    thief_runner = PeerRunner(thief_side, thief, LoopbackClient(PeerHandlers(cop_config, cop)))

    async def drive():
        return await asyncio.gather(cop_runner.run_sub_game(), thief_runner.run_sub_game())

    cop_outcome, thief_outcome = asyncio.run(drive())

    assert cop_outcome.outcome == constants.OUTCOME_CAPTURE
    assert thief_outcome.outcome == constants.OUTCOME_CAPTURE
    assert cop_outcome.steps == 1  # caught on the first move, not at the ceiling
    assert thief.i_am_caught


def test_the_thief_never_claims_a_capture(peer_config, thief_config):
    """Only a cop may claim one -- a thief has nothing to capture."""
    thief = PeerSession(config=thief_config, role=constants.ROLE_THIEF, game_id=GAME_ID, seed=2)
    thief.prepare_step(1)
    assert thief.capture_claim() is None


def test_a_claim_on_the_wrong_cell_is_answered_honestly(peer_config, thief_config):
    """Rule 22 cuts both ways: no false confirmation either."""
    thief = PeerSession(config=thief_config, role=constants.ROLE_THIEF, game_id=GAME_ID, seed=2)
    thief.prepare_step(1)
    mine = thief.pending_cell()
    elsewhere = [(mine[0] + 2) % 7, (mine[1] + 3) % 7]
    assert thief.answer_capture_claim(elsewhere) is False
    assert thief.answer_capture_claim(list(mine)) is True
    assert thief.i_am_caught
