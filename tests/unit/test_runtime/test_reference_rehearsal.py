"""Two reference-v3 drivers playing a whole sub-game against each other.

Not a substitute for the two-process rehearsal -- rules 1 and 2 make a real
match cross a socket, and an in-process wire cannot see a missing header, a
half-closed stream or an argument name FastMCP refuses. What it *can* see is
everything above the transport, and that is where every one of this league's
failures except one has actually lived: the wrong side opening, a step number
that repeats, a claim never answered, two peers settling one sub-game two
different ways.

Both sides run the real driver, push through the real validator, and audit each
other's real chain at the end. Nothing about the game is stubbed except the
socket between them.
"""

from __future__ import annotations

import asyncio

from p2pchase import constants
from p2pchase.domain.brains import Decision
from p2pchase.mcp.reference_v3 import refuse_turn
from p2pchase.mcp.reference_v3_server import Inboxes, register_reference_v3
from p2pchase.runtime.peer_session import PeerSession
from p2pchase.runtime.reference_driver import ReferenceDriver


class _Recorder:
    def __init__(self) -> None:
        self.tools: dict = {}

    def tool(self, fn):
        self.tools[fn.__name__] = fn
        return fn


class _Wire:
    """Delivers into the opponent's inbox through their real tool bindings."""

    def __init__(self, far: Inboxes) -> None:
        recorder = _Recorder()
        register_reference_v3(recorder, far)
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


def _match(peer_config):
    """A cop and a thief wired to each other, plus both wires."""
    cop_in, thief_in = Inboxes(), Inboxes()
    cop_wire, thief_wire = _Wire(thief_in), _Wire(cop_in)
    cop = ReferenceDriver(
        peer_config,
        PeerSession(config=peer_config, role=constants.ROLE_COP, game_id="a-vs-b"),
        cop_wire, cop_in)
    thief = ReferenceDriver(
        peer_config,
        PeerSession(config=peer_config, role=constants.ROLE_THIEF, game_id="a-vs-b"),
        thief_wire, thief_in)
    return cop, thief, cop_wire, thief_wire


def _play(peer_config):
    cop, thief, cop_wire, thief_wire = _match(peer_config)

    async def both():
        return await asyncio.gather(cop.run_sub_game(), thief.run_sub_game())

    cop_outcome, thief_outcome = asyncio.run(both())
    return cop, thief, cop_wire, thief_wire, cop_outcome, thief_outcome


def test_a_whole_sub_game_runs_to_a_settled_ending(peer_config):
    *_, cop_outcome, thief_outcome = _play(peer_config)
    assert cop_outcome.outcome in (constants.OUTCOME_CAPTURE, constants.OUTCOME_SURVIVAL)
    assert thief_outcome.outcome == cop_outcome.outcome, (
        "two reports of one sub-game that disagree void the match for both (rule 35)")


def test_nobody_stalls_into_a_technical_loss(peer_config):
    """Rule 6 charges both teams, so a stall is the outcome worth pinning against."""
    *_, cop_outcome, thief_outcome = _play(peer_config)
    assert constants.OUTCOME_TECHNICAL_LOSS not in (cop_outcome.outcome,
                                                    thief_outcome.outcome)


def test_the_thief_moves_first(peer_config):
    """Their rule. A cop that opens is a move ahead for the whole sub-game."""
    _cop, thief, cop_wire, thief_wire, *_ = _play(peer_config)
    assert thief.we_open
    assert thief_wire.turns[0]["step"] == 1
    assert thief_wire.turns[0]["sender"] == "thief"
    assert cop_wire.turns[0]["step"] == 1, "both sides number the same round alike"


def test_every_message_either_side_sent_passes_the_other_validator(peer_config):
    _cop, _thief, cop_wire, thief_wire, *_ = _play(peer_config)
    for wire in (cop_wire, thief_wire):
        assert [refuse_turn(t) for t in wire.turns] == [""] * len(wire.turns)


def test_neither_side_ever_announced_two_payloads_under_one_step(peer_config):
    """The audit is keyed on the step number, so a repeat reports as a forgery."""
    _cop, _thief, cop_wire, thief_wire, *_ = _play(peer_config)
    for wire in (cop_wire, thief_wire):
        steps = [t["step"] for t in wire.turns]
        assert steps == sorted(set(steps)), steps


def test_the_two_chains_audit_each_other_clean(peer_config):
    """Rule 36. An honest game that fails its own audit is worth nothing."""
    *_, cop_outcome, thief_outcome = _play(peer_config)
    assert cop_outcome.opponent_audit.get("passed") is True
    assert thief_outcome.opponent_audit.get("passed") is True


def test_both_inboxes_are_empty_once_the_sub_game_has_settled(peer_config):
    """Otherwise the next sub-game's first wait finds a stale turn and desyncs."""
    cop, thief, *_ = _play(peer_config)
    for driver in (cop, thief):
        assert not driver.inboxes.turns
        assert not driver.inboxes.audits


def test_every_capture_claim_the_cop_made_was_answered(peer_config):
    """Rule 22 makes the answer compulsory, and their wire has no response body.

    Every one, including the claim made on the final round -- that is what the
    terminal message is for. An off-by-one here is not cosmetic: the unanswered
    claim would be the one that decides whether the cop won.
    """
    _cop, _thief, cop_wire, thief_wire, *_ = _play(peer_config)
    claims = [t for t in cop_wire.turns if t.get("capture_claim") is not None]
    answers = [t for t in thief_wire.turns if t.get("claim_response") is not None]
    assert len(answers) == len(claims)


def test_the_thief_closes_the_sub_game_with_one_extra_sealed_step(peer_config):
    """35 rounds each, then the thief's terminal message. The cop sends none."""
    _cop, _thief, cop_wire, thief_wire, *_ = _play(peer_config)
    assert len(thief_wire.turns) == len(cop_wire.turns) + 1


def test_the_thief_declares_its_survival_on_the_wire(peer_config):
    """Only the thief can see this ending, so only the thief can state it."""
    _cop, _thief, _cop_wire, thief_wire, cop_outcome, _ = _play(peer_config)
    assert cop_outcome.outcome == constants.OUTCOME_SURVIVAL
    assert thief_wire.turns[-1]["win_claim"] == {"type": "survival", "steps": 35}


def _play_to_capture(peer_config):
    """The same rehearsal with a thief that refuses to run.

    An unforced game ends in survival, which never reaches the concession path
    -- and that path is the one the kit rates its worst failure, so a test that
    quietly skipped it would be worse than no test. Pinning the thief to
    ``STAY`` makes the capture arrive on its own rather than being injected:
    the cop still has to find it through the trail, and every message is the
    one the real driver would have sent.
    """
    cop, thief, cop_wire, thief_wire = _match(peer_config)
    thief.session.brain.decide = lambda state: Decision(move="STAY")

    async def both():
        return await asyncio.gather(cop.run_sub_game(), thief.run_sub_game())

    cop_outcome, thief_outcome = asyncio.run(both())
    return cop, thief, cop_wire, thief_wire, cop_outcome, thief_outcome


def test_a_stationary_thief_is_actually_caught(peer_config):
    """Guards the guard: if the cop never wins, the tests below prove nothing."""
    *_, cop_outcome, thief_outcome = _play_to_capture(peer_config)
    assert cop_outcome.outcome == constants.OUTCOME_CAPTURE
    assert thief_outcome.outcome == constants.OUTCOME_CAPTURE


def test_a_capture_is_conceded_rather_than_left_for_the_cop_to_infer(peer_config):
    """The kit's worst failure: a caught thief that simply stops.

    The cop cannot see the board, so silence here leaves it waiting out its
    budget and settling as a timeout a sub-game it won -- two reports of one
    game that disagree, which rule 35 voids for both teams.
    """
    *_, thief_wire, _, _ = _play_to_capture(peer_config)
    final = thief_wire.turns[-1]
    assert final.get("claim_response", {}).get("caught") is True
    assert refuse_turn(final) == "", "the concession must be a turn they accept"


def test_the_conceding_turn_is_a_freshly_sealed_step(peer_config):
    """Not a resent commitment: one hash over two payloads is equivocation."""
    _cop, thief, _cop_wire, thief_wire, *_ = _play_to_capture(peer_config)
    commits = [t["commit"] for t in thief_wire.turns]
    assert len(commits) == len(set(commits))
    assert commits[-1] in {r["commit"] for r in thief.session.records}


def test_the_conceded_step_survives_the_cops_audit(peer_config):
    """The terminal record is audited like any other, so it has to verify."""
    *_, cop_outcome, _ = _play_to_capture(peer_config)
    assert cop_outcome.opponent_audit.get("passed") is True
