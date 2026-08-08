"""What the reference-v3 driver does when the other side stops behaving.

The happy path is covered by the rehearsal. These are the paths rule 6 charges
for, and they matter more than they look: an unfinished sub-game is a technical
loss for *both* teams, so every one of them has to end in a stated outcome and
a disclosed chain rather than in a hang or a traceback.
"""

from __future__ import annotations

import asyncio

import pytest

from p2pchase import constants
from p2pchase.mcp.reference_v3_server import Inboxes
from p2pchase.runtime.peer_session import PeerSession
from p2pchase.runtime.reference_driver import ReferenceDriver
from p2pchase.runtime.watchdog import DeadlineExceededError


class _Silent:
    """A peer that accepts everything and never says anything back."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict]] = []

    async def call(self, tool: str, payload: dict | None = None) -> dict:
        self.sent.append((tool, payload or {}))
        return {"ok": True}


class _Gone:
    """A peer whose process has exited mid-message."""

    async def call(self, tool: str, payload: dict | None = None) -> dict:
        raise ConnectionError("connection reset by peer")


def _driver(peer_config, client, role: str = constants.ROLE_COP) -> ReferenceDriver:
    session = PeerSession(config=peer_config, role=role, game_id="a-vs-b")
    driver = ReferenceDriver(peer_config, session, client, Inboxes())
    # One second, not the agreed thirty: these tests are about which branch runs,
    # not about how patient the real driver is.
    driver.turn_timeout = 0.0
    return driver


def _run(coro):
    return asyncio.run(coro)


def test_a_peer_that_never_moves_ends_as_a_technical_loss_not_a_hang(peer_config):
    """Stated plainly, because rule 6 charges us either way and silence helps nobody."""
    driver = _driver(peer_config, _Silent())
    outcome = _run(driver.run_sub_game())
    assert outcome.outcome == constants.OUTCOME_TECHNICAL_LOSS


def test_a_stalled_sub_game_still_discloses_our_chain(peer_config):
    """Rule 18 does not have an exception for a game that went wrong."""
    client = _Silent()
    _run(_driver(peer_config, client).run_sub_game())
    assert [tool for tool, _ in client.sent] == ["submit_audit"]


def test_their_audit_arriving_instead_of_a_turn_settles_the_sub_game(peer_config):
    """A reference-v3 peer says "I have stopped" by disclosing its chain."""
    driver = _driver(peer_config, _Silent())
    driver.inboxes.audits.append(
        {"sender": "thief", "records": [], "result_claim": constants.OUTCOME_CAPTURE})
    outcome = _run(driver.run_sub_game())
    assert outcome.outcome == constants.OUTCOME_CAPTURE


def test_an_audit_with_no_stated_ending_is_read_as_survival(peer_config):
    """A peer that ran the horizon out has nothing to declare (opponent_ending)."""
    driver = _driver(peer_config, _Silent())
    driver.inboxes.audits.append({"sender": "thief", "records": []})
    assert _run(driver.run_sub_game()).outcome == constants.OUTCOME_SURVIVAL


def test_a_shouted_outcome_is_folded_to_something_the_score_table_knows(peer_config):
    """``ScoreTable.award`` raises on ``'CAPTURE'``; an opponent's casing is not ours."""
    driver = _driver(peer_config, _Silent())
    driver.inboxes.audits.append({"sender": "thief", "records": [], "result_claim": "CAPTURE"})
    assert _run(driver.run_sub_game()).outcome == constants.OUTCOME_CAPTURE


def test_a_peer_that_has_exited_does_not_take_us_down_with_it(peer_config):
    """We were mid-message to a process that no longer exists. Not a fault."""
    outcome = _run(_driver(peer_config, _Gone()).run_sub_game())
    assert outcome.outcome == constants.OUTCOME_TECHNICAL_LOSS
    assert outcome.records == [] or outcome.records is not None


def test_a_failed_audit_submission_is_logged_and_survived(peer_config, caplog):
    driver = _driver(peer_config, _Gone())
    with caplog.at_level("WARNING"):
        _run(driver.exchange_chains(constants.OUTCOME_SURVIVAL))
    assert "could not submit our audit" in caplog.text


def test_an_audit_that_never_arrives_costs_the_proof_and_not_the_game(peer_config,
                                                                      caplog):
    """Rule 36 is about verifying their chain; we cannot verify what never came."""
    driver = _driver(peer_config, _Silent())
    with caplog.at_level("WARNING"):
        verdict = _run(driver.exchange_chains(constants.OUTCOME_SURVIVAL))
    assert verdict == {}
    assert "their chain is unverified" in caplog.text


def test_their_chain_is_verified_when_it_does_arrive(peer_config):
    driver = _driver(peer_config, _Silent())
    driver.inboxes.audits.append({"sender": "thief", "records": []})
    assert _run(driver.exchange_chains(constants.OUTCOME_SURVIVAL)) != {}


def test_the_inbox_is_emptied_even_when_the_sub_game_went_wrong(peer_config):
    """A stale turn surviving into the next sub-game desyncs it from move one."""
    driver = _driver(peer_config, _Silent())
    driver.inboxes.turns.append({"step": 99})
    _run(driver.exchange_chains(constants.OUTCOME_TECHNICAL_LOSS))
    assert not driver.inboxes.turns


def test_the_outcome_we_disclose_is_the_one_we_settled_on(peer_config):
    """Their auditor reads ``result_claim``; a wrong one disagrees with our report."""
    client = _Silent()
    driver = _driver(peer_config, client)
    _run(driver.exchange_chains(constants.OUTCOME_CAPTURE))
    _tool, payload = client.sent[0]
    assert payload["payload"]["result_claim"] == constants.OUTCOME_CAPTURE
    assert payload["payload"]["sender"] == "police"


def test_a_deadline_still_fires_when_nothing_is_queued(peer_config):
    """Guards the guard: these tests would prove nothing against an infinite wait."""
    driver = _driver(peer_config, _Silent())
    with pytest.raises(DeadlineExceededError):
        _run(driver.receive(1))
