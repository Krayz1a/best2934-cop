"""The reference-v3 driver, one behaviour at a time.

Everything pushed here goes through the *real* validator on the way out --
:func:`register_reference_v3` bound to a recorder -- so a message this driver
builds and a conformant peer would refuse fails here rather than in a match.
That is the whole lesson of 8 August: both sides had agreed fourteen hashed
terms and neither had ever put a message through the other's front door.

The two orderings are asserted separately because the thief opening is theirs,
not ours, and getting it backwards puts a peer a move ahead for a whole
sub-game with every commitment keyed to the wrong round.
"""

from __future__ import annotations

import asyncio

from p2pchase import constants
from p2pchase.mcp.reference_v3 import refuse_turn
from p2pchase.mcp.reference_v3_server import Inboxes, register_reference_v3
from p2pchase.runtime.peer_session import PeerSession
from p2pchase.runtime.reference_driver import ReferenceDriver, now_iso


class _Recorder:
    """Stands in for FastMCP, exactly as the binding tests do."""

    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, fn):
        self.tools[fn.__name__] = fn
        return fn


class _Wire:
    """An outbound client whose far end is a real reference-v3 server.

    Keeps every message it sent, so a test can assert on what actually crossed
    rather than on what the driver meant to send.
    """

    def __init__(self, inboxes: Inboxes) -> None:
        recorder = _Recorder()
        register_reference_v3(recorder, inboxes)
        self._tools = recorder.tools
        self.sent: list[tuple[str, dict]] = []

    async def call(self, tool: str, payload: dict | None = None) -> dict:
        payload = payload or {}
        body = payload.get("message", payload.get("payload", {}))
        self.sent.append((tool, body))
        return self._tools[tool](body)

    @property
    def turns(self) -> list[dict]:
        return [body for name, body in self.sent if name == "receive_turn"]


def _driver(peer_config, role: str) -> tuple[ReferenceDriver, _Wire, Inboxes]:
    """A driver whose pushes land in ``far`` and whose inbox is ``near``."""
    session = PeerSession(config=peer_config, role=role, game_id="a-vs-b")
    near, far = Inboxes(), Inboxes()
    wire = _Wire(far)
    return ReferenceDriver(peer_config, session, wire, near), wire, near


def _run(coro):
    return asyncio.run(coro)


def test_we_open_is_true_for_the_thief_and_false_for_the_police(peer_config):
    """SPEC 7.5, and the opposite of our own protocol and gal-roy1's."""
    thief, _, _ = _driver(peer_config, constants.ROLE_THIEF)
    police, _, _ = _driver(peer_config, constants.ROLE_COP)
    assert thief.we_open and not police.we_open


def test_our_own_turn_passes_their_validator(peer_config):
    """The check that would have saved the evening of 8 August."""
    driver, wire, _ = _driver(peer_config, constants.ROLE_THIEF)
    _run(driver.act(1, response=None))
    assert refuse_turn(wire.turns[0]) == ""


def test_the_timestamp_is_present_and_not_the_empty_string(peer_config):
    """Their hard requirement, and the kit's own sparring peer gets it wrong."""
    driver, wire, _ = _driver(peer_config, constants.ROLE_THIEF)
    _run(driver.act(1, response=None))
    assert wire.turns[0]["timestamp"]
    assert now_iso()


def test_the_sender_is_their_lowercase_spelling(peer_config):
    driver, wire, _ = _driver(peer_config, constants.ROLE_THIEF)
    _run(driver.act(1, response=None))
    assert wire.turns[0]["sender"] == "thief"


def test_an_owed_claim_answer_rides_on_our_next_turn(peer_config):
    """Their wire has no response body, so this is the only way home (rule 22)."""
    driver, wire, _ = _driver(peer_config, constants.ROLE_THIEF)
    owed = {"claim": [1, 1], "caught": False}
    _run(driver.act(2, response=owed))
    assert wire.turns[0]["claim_response"] == owed


def test_the_terminal_message_is_a_valid_turn_carrying_the_answer(peer_config):
    """A caught thief still owes a message their validator will accept."""
    driver, wire, _ = _driver(peer_config, constants.ROLE_THIEF)
    answer = {"claim": [3, 3], "caught": True}
    _run(driver.finish(6, answer))
    message = wire.turns[0]
    assert refuse_turn(message) == ""
    assert message["claim_response"] == answer
    assert message["step"] == 6
    assert message["hint"], "an empty sentence at the audit is a hole in the chain"


def test_the_terminal_sentence_sealed_and_the_one_sent_are_the_same(peer_config):
    """Sealing one hint and disclosing another fails the audit it exists to survive."""
    driver, wire, _ = _driver(peer_config, constants.ROLE_THIEF)
    _run(driver.finish(3, None))
    sent = wire.turns[0]["hint"]
    assert any(r["payload"]["hint"] == sent for r in driver.session.final_reveal())


def test_a_thief_that_owes_an_answer_sends_a_terminal_even_though_it_got_away(
        peer_config):
    """The cop claims on *every* round, including the last.

    Answering only when caught leaves that final claim hanging, and a cop
    cannot tell "you missed" from "I have gone" -- so it settles as survival a
    sub-game it may have won. Rule 35 voids a disagreement like that for both.
    """
    driver, wire, _ = _driver(peer_config, constants.ROLE_THIEF)
    driver.owed = {"claim": [4, 4], "caught": False}
    _run(driver.wrap_up(36))
    assert wire.turns[0]["claim_response"] == {"claim": [4, 4], "caught": False}
    assert refuse_turn(wire.turns[0]) == ""


def test_only_one_terminal_step_is_ever_sealed(peer_config):
    """A second would put two records past the end of a closed sub-game."""
    driver, wire, _ = _driver(peer_config, constants.ROLE_THIEF)
    _run(driver.wrap_up(36))
    _run(driver.wrap_up(37))
    assert len(wire.turns) == 1


def test_the_police_sends_no_terminal_message_and_waits_for_theirs(peer_config):
    """It meets none of the three conditions, and its claim is the one outstanding."""
    driver, wire, inboxes = _driver(peer_config, constants.ROLE_COP)
    driver.turn_timeout = 0.0
    driver.loop.claimed = (2, 2)
    _run(driver.wrap_up(36))
    assert wire.turns == []


def test_a_police_terminal_wait_reads_the_concession_that_arrives(peer_config):
    driver, _wire, inboxes = _driver(peer_config, constants.ROLE_COP)
    driver.loop.claimed = (2, 2)
    inboxes.turns.append({"step": 36, "sender": "thief", "commit": "b" * 64,
                          "hint": "", "smell_grid": {}, "timestamp": "t",
                          "claim_response": {"claim": [2, 2], "caught": True}})
    _run(driver.wrap_up(36))
    assert driver.loop.finished == constants.OUTCOME_CAPTURE


def test_the_conceded_step_joins_the_chain_and_is_disclosed(peer_config):
    """Withholding it would read as concealment at exactly the wrong moment."""
    driver, wire, _ = _driver(peer_config, constants.ROLE_THIEF)
    _run(driver.finish(4, {"claim": [0, 0], "caught": True}))
    disclosed = {r["commit"] for r in driver.session.final_reveal()}
    assert wire.turns[0]["commit"] in disclosed


def test_a_concession_never_reuses_an_earlier_commitment(peer_config):
    """Two payloads under one hash is equivocation, not economy."""
    driver, wire, _ = _driver(peer_config, constants.ROLE_THIEF)
    _run(driver.act(1, response=None))
    _run(driver.finish(2, {"claim": [0, 0], "caught": True}))
    first, second = (t["commit"] for t in wire.turns)
    assert first != second


def test_a_refusal_from_them_is_logged_rather_than_raised(peer_config, caplog):
    """A stall with no explanation on either side is the expensive outcome."""
    driver, _, _ = _driver(peer_config, constants.ROLE_THIEF)
    with caplog.at_level("ERROR"):
        _run(driver.push_turn({"step": 1, "sender": "thief", "commit": "not-hex"}))
    assert "refused our turn" in caplog.text


def test_a_conceding_opponent_settles_the_sub_game_as_our_capture(peer_config):
    driver, _, _ = _driver(peer_config, constants.ROLE_COP)
    driver.loop.claimed = (2, 2)
    driver._read_concession({"claim_response": {"claim": [2, 2], "caught": True}})
    assert driver.loop.finished == constants.OUTCOME_CAPTURE


def test_a_concession_we_never_claimed_is_not_believed(peer_config):
    """"You caught me" is the one direction in which a lie would pay us."""
    driver, _, _ = _driver(peer_config, constants.ROLE_COP)
    driver._read_concession({"claim_response": {"claim": [2, 2], "caught": True}})
    assert driver.loop.finished == ""
