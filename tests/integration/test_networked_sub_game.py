"""A whole sub-game played across the MCP protocol (rules 10, 11, 19, 36).

The local harness in :mod:`p2pchase.runtime.local_match` shares a process and a
convenient function call. This test does not: every belief update on either side
arrives through a real protocol message, handled by the same
:class:`~p2pchase.mcp.handlers.PeerHandlers` a socket would deliver it to. The
only thing removed is the socket itself, which rules 1 and 2 forbid us from
removing in a *match* but which has nothing to say about the protocol's
correctness.

What this is here to catch is the class of bug a single-process harness cannot
see: state that the local path updates directly and the networked path never
receives, so a strategy tuned in rehearsal behaves differently in a real game.
"""

from __future__ import annotations

import asyncio

import pytest

from p2pchase import constants
from p2pchase.domain.crypto import audit_records
from p2pchase.mcp.client import LoopbackClient
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.runtime.peer import PeerRunner
from p2pchase.runtime.peer_session import PeerSession

GAME_ID = "best2934_vs_rival999"


def _wire_two_peers(peer_config, thief_config, steps: int):
    """Two full peers, each holding a client pointed at the other's handlers."""
    cop = PeerSession(config=peer_config, role=constants.ROLE_COP, game_id=GAME_ID, seed=5)
    thief = PeerSession(config=thief_config, role=constants.ROLE_THIEF, game_id=GAME_ID, seed=6)

    cop_handlers = PeerHandlers(peer_config, cop)
    thief_handlers = PeerHandlers(thief_config, thief)

    cop_runner = PeerRunner(peer_config, cop, LoopbackClient(thief_handlers))
    thief_runner = PeerRunner(thief_config, thief, LoopbackClient(cop_handlers))
    return cop, thief, cop_runner, thief_runner


def _play(peer_config, thief_config, steps: int = 8):
    """Drive both peers concurrently, as two live agents would run."""
    cop, thief, cop_runner, thief_runner = _wire_two_peers(peer_config, thief_config, steps)

    async def drive() -> None:
        for step in range(1, steps + 1):
            # Both peers push and wait at the same time. Running them
            # sequentially would hide exactly the deadlock this exercises.
            await asyncio.gather(cop_runner.play_step(step), thief_runner.play_step(step))

    asyncio.run(drive())
    return cop, thief


def test_a_sub_game_runs_end_to_end_over_the_protocol(peer_config, thief_config):
    cop, thief = _play(peer_config, thief_config)
    assert cop.state.step == thief.state.step == 8
    assert len(cop.records) == len(thief.records) == 8


def test_each_side_saw_every_one_of_the_others_steps(peer_config, thief_config):
    """A peer that quietly missed a reveal would still finish, with a wrong belief."""
    cop, thief = _play(peer_config, thief_config)
    assert cop.state.opponent_steps_seen == 8
    assert thief.state.opponent_steps_seen == 8
    assert sorted(cop.opponent_commitments) == list(range(1, 9))


def test_both_commit_chains_verify_after_the_final_reveal(peer_config, thief_config):
    """Rule 19: the disclosure has to reproduce the hashes sealed at the time."""
    cop, thief = _play(peer_config, thief_config)
    assert audit_records(cop.final_reveal()).passed
    assert audit_records(thief.final_reveal()).passed


def test_each_peer_can_audit_the_other(peer_config, thief_config):
    """Rule 36: the mutual audit is what replaces a referee."""
    cop, thief = _play(peer_config, thief_config)
    assert cop.audit(thief.final_reveal())["passed"] is True
    assert thief.audit(cop.final_reveal())["passed"] is True


def test_a_tampered_log_fails_the_opponents_audit(peer_config, thief_config):
    """The whole integrity story rests on this failing, so it is asserted."""
    cop, thief = _play(peer_config, thief_config)
    records = thief.final_reveal()
    # records[3] is the fourth record, i.e. step 4 -- the audit names steps, and
    # a test that accepted any failing step would not prove it names the right one.
    records[3] = {**records[3], "payload": {**records[3]["payload"], "move": "STAY"}}

    verdict = cop.audit(records)
    assert verdict["passed"] is False
    assert verdict["failed_steps"] == [4]
    assert verdict["verified_steps"] == 7


def test_belief_actually_moved_over_the_wire(peer_config, thief_config):
    """The point of the protocol is that information crosses it.

    A peer whose posterior is still the uniform prior after eight steps received
    nothing usable, even though every message was delivered -- which is the
    silent failure mode this whole test module exists for.
    """
    cop, thief = _play(peer_config, thief_config)
    for session in (cop, thief):
        assert session.state.belief.entropy() < 5.0
        assert session.state.opponent_scent.grid, "no trail was ever sampled"


def test_a_reveal_without_a_prior_commitment_is_refused(peer_config):
    """Accepting one would make the commitment optional, and with it the audit."""
    session = PeerSession(config=peer_config, role=constants.ROLE_COP, game_id=GAME_ID)
    with pytest.raises(ValueError, match="without a prior commitment"):
        session.on_reveal(1, "N", "heading north", None)
