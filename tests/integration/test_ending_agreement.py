"""The three ways a finished sub-game used to end in a technical loss anyway.

Each of these was found by ``tools/rehearsal.py``, not by the suite, and each
had the same shape: two honest peers, a sub-game that ended correctly, and a
protocol that could not carry the ending from one side to the other. In a league
match all three score zero -- rule 6 for a stalled sub-game, rule 35 for two
reports that contradict each other.

They are pinned here because a socket is not needed to reproduce any of them
once you know they exist. Finding them needed one; keeping them fixed does not.
"""

from __future__ import annotations

import asyncio

import pytest

from p2pchase import constants
from p2pchase.domain.board import IllegalMoveError, build_board
from p2pchase.domain.own_state import build_own_state
from p2pchase.mcp import contracts
from p2pchase.mcp.client import LoopbackClient
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.reports.result import SubGameOutcome, build_result_artifact
from p2pchase.runtime.peer import PeerRunner
from p2pchase.runtime.peer_session import PeerSession

GAME_ID = "best2934_vs_endings"


def _outcome(number: int, mine: str, theirs: str, started: str, tokens: int) -> SubGameOutcome:
    """One sub-game as *one* team records it -- including its private fields."""
    return SubGameOutcome(
        sub_game_number=number,
        roles={mine: constants.ROLE_COP, theirs: constants.ROLE_THIEF},
        started_at=started,
        ended_at=started,
        result=constants.OUTCOME_CAPTURE,
        winner_group=mine,
        github_commit={mine: "abc123"},
        tokens={mine: tokens},
        score={mine: 20, theirs: 5},
        log_files={mine: f"log_{GAME_ID}_g0{number}.json"},
        audit={"passed": True},
    )


def test_two_honest_teams_produce_the_same_agreement_digest(peer_config):
    """Rule 35: a digest that never matches accuses both teams of contradicting.

    The two reports below describe one match from either side, and differ in
    every field a peer computes privately: clocks, tokens, commit, log names,
    who audited whom, and a locally minted ``game_uid``. If any of that reached
    the digest, two honest teams would file "contradictory" reports every time.
    """
    ours = build_result_artifact(
        GAME_ID, "uid-ours", ["best2934", "rival42"],
        [_outcome(1, "best2934", "rival42", "2026-08-04T10:00:00.100000+00:00", 120)],
        {"total_score": {"best2934": 20, "rival42": 5}, "winner_group": "best2934",
         "sub_games_won": {"best2934": 1, "rival42": 0}, "ties": 0, "series_tie": False},
        {"best2934": 120},
    )
    # The same match as the opponent records it: same roles, same score, same
    # ending -- but their clock, their token count, their commit and their uid.
    theirs = build_result_artifact(
        GAME_ID, "uid-theirs", ["rival42", "best2934"],
        [_outcome(1, "best2934", "rival42", "2026-08-04T10:00:00.999999+00:00", 84)],
        {"total_score": {"rival42": 5, "best2934": 20}, "winner_group": "best2934",
         "sub_games_won": {"rival42": 0, "best2934": 1}, "ties": 0, "series_tie": False},
        {"rival42": 84},
    )
    assert ours["mutual_agreement"]["sha256"] == theirs["mutual_agreement"]["sha256"]
    assert ours["game_uid"] != theirs["game_uid"]  # private, and rightly excluded
    assert ours["sub_games"][0]["tokens"] != theirs["sub_games"][0]["tokens"]


def test_a_disagreement_about_the_result_still_breaks_the_digest(peer_config):
    """The digest must stay sensitive to the thing it exists to detect."""
    honest = build_result_artifact(
        GAME_ID, "uid", ["best2934", "rival42"],
        [_outcome(1, "best2934", "rival42", "2026-08-04T10:00:00+00:00", 10)],
        {"total_score": {"best2934": 20, "rival42": 5}, "winner_group": "best2934"},
        {"best2934": 10},
    )
    liar = _outcome(1, "best2934", "rival42", "2026-08-04T10:00:00+00:00", 10)
    liar.winner_group = "rival42"
    disputed = build_result_artifact(
        GAME_ID, "uid", ["best2934", "rival42"], [liar],
        {"total_score": {"best2934": 20, "rival42": 5}, "winner_group": "best2934"},
        {"best2934": 10},
    )
    assert honest["mutual_agreement"]["sha256"] != disputed["mutual_agreement"]["sha256"]


def test_a_move_walled_off_after_it_was_committed_stands_still(shared_config):
    """The mover was honest and the board changed under it (rules 15, 17).

    A move is sealed a whole exchange before the barrier for that same step is
    revealed. Raising on the collision would end a sub-game that neither peer
    did anything wrong in.
    """
    state = build_own_state(shared_config, constants.ROLE_THIEF, build_board(shared_config))
    state.position = (3, 3)
    assert state.settle_move("E") == (3, 4)

    state.board.barriers.add((3, 4))
    assert state.settle_move("E") == (3, 3), "a walled-off move must not be applied"
    state.apply_own_move("E")
    assert state.position == (3, 3)


def test_walking_off_the_board_is_still_a_fault(shared_config):
    """Only the barrier collision is forgiven; a brain bug must still surface."""
    state = build_own_state(shared_config, constants.ROLE_THIEF, build_board(shared_config))
    state.position = (0, 0)
    with pytest.raises(IllegalMoveError):
        state.settle_move("N")


def test_a_peer_that_stops_first_tells_the_other_how_it_ended(peer_config, thief_config):
    """Rule 47: only the thief can see it is boxed in, so it has to say so.

    Before this, the cop waited out its 30-second deadline for a commitment that
    was never coming and booked a technical loss -- for a sub-game it had won.
    """
    cop = PeerSession(peer_config, constants.ROLE_COP, GAME_ID, seed=1)
    thief = PeerSession(thief_config, constants.ROLE_THIEF, GAME_ID, seed=2)
    runner = PeerRunner(peer_config, cop, LoopbackClient(PeerHandlers(thief_config, thief)))

    assert not cop.opponent_finished
    # What the thief's final reveal looks like when it arrives at our server.
    PeerHandlers(peer_config, cop).final_reveal(
        contracts.final_reveal_payload(GAME_ID, 1, thief.group_id, thief.final_reveal(),
                                       constants.OUTCOME_CAPTURE))
    assert cop.opponent_finished == constants.OUTCOME_CAPTURE

    outcome = asyncio.run(runner.run_sub_game())
    assert outcome.outcome == constants.OUTCOME_CAPTURE
    assert not outcome.aborted, "an announced ending is an ending, not a fault"
