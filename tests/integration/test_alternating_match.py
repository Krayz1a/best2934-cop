"""A whole sub-game played through gal-roy1's alternating dialect (I-7).

The other integration tests drive our own simultaneous protocol. This one never
touches it: every round is a ``TurnMessage`` into ``submit_turn`` and a
``reply_turn`` back, exactly as a match they drive would run, with the cop
moving first after a nil handover.

What it exists to catch is the class of bug that only appears when two boards
advance independently -- a round counter that drifts, a commitment recorded
against the wrong step, a survival clock that fires on one side and not the
other. All of those pass a unit test of either half.
"""

from __future__ import annotations

import itertools

import pytest

from p2pchase import constants
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.mcp.interop import InteropAdapter
from p2pchase.mcp.turn_message import nil_turn
from p2pchase.runtime.peer_session import PeerSession

GAME_ID = "best2934-vs-gal-roy1"


@pytest.fixture
def peers(peer_config, thief_config):
    """Two adapters, each over its own private session. No shared board."""
    cop = PeerSession(peer_config, constants.ROLE_COP, GAME_ID, seed=5)
    thief = PeerSession(thief_config, constants.ROLE_THIEF, GAME_ID, seed=6)
    return (InteropAdapter(PeerHandlers(peer_config, cop)),
            InteropAdapter(PeerHandlers(thief_config, thief)))


def _play(cop_side, thief_side, rounds: int):
    """Drive the alternating loop; the thief opens with a nil handover.

    Stops on a *complete* round -- ``rounds * 2`` half-moves, cop first. Ending
    mid-round would leave the cop one action ahead, which is correct behaviour
    and a confusing thing for a test to assert equality against.

    Returns every answer, so a caller can assert on the exchange rather than
    only on the wreckage afterwards.
    """
    answers = []
    # The thief cannot move first, so it hands the token over without acting.
    turn = cop_side.submit_turn(nil_turn(constants.ROLE_THIEF))
    answers.append(turn)

    sides = itertools.cycle((thief_side, cop_side))
    for _ in range(rounds * 2 - 1):
        if "reply_turn" not in turn:
            break
        turn = next(sides).submit_turn(turn["reply_turn"])
        answers.append(turn)
    return answers


def test_a_nil_opening_does_not_advance_the_round_counter(peers):
    """Their pinned rule. A handover is not a round, because nobody acted."""
    cop_side, _ = peers
    assert cop_side.turns(cop_side.handlers.session).round == 0

    answer = cop_side.submit_turn(nil_turn(constants.ROLE_THIEF))

    assert answer["reply_turn"]["step"] == 1
    assert cop_side.turns(cop_side.handlers.session).round == 1


def test_both_peers_stay_on_the_same_round(peers):
    """A drift of more than one is a survival clock that fires on one side only."""
    cop_side, thief_side = peers
    _play(cop_side, thief_side, rounds=6)

    cop = cop_side.handlers.session
    thief = thief_side.handlers.session
    assert cop.state.step == thief.state.step == 6
    assert len(cop.records) == len(thief.records) == 6


def test_mid_round_the_first_mover_is_ahead_by_exactly_one(peers):
    """The invariant that actually holds during play, and it is not equality.

    Alternating turns mean that between the two halves of a round one side has
    acted and the other has not. Asserting equality at an arbitrary moment
    would be asserting that the protocol is simultaneous, which is the whole
    thing this dialect is not.
    """
    cop_side, thief_side = peers
    _play(cop_side, thief_side, rounds=4)
    cop = cop_side.handlers.session
    thief = thief_side.handlers.session

    # Open a fifth round without closing it.
    cop_side.turns(cop).take_turn(5)

    assert cop.state.step - thief.state.step == 1


def test_every_round_seals_a_commitment_the_other_side_recorded(peers):
    """The audit is only possible if each side held the other's seals live."""
    cop_side, thief_side = peers
    _play(cop_side, thief_side, rounds=6)

    cop = cop_side.handlers.session
    thief = thief_side.handlers.session

    # The thief holds all six of the cop's seals; the cop holds five, because
    # the thief's sixth turn was still in flight when the loop stopped. That
    # asymmetry is inherent to alternating play rather than a fault -- whoever
    # moves last always has a turn nobody has received yet.
    assert sorted(thief.opponent_commitments) == [1, 2, 3, 4, 5, 6]
    assert sorted(cop.opponent_commitments) == [1, 2, 3, 4, 5]


def test_no_turn_message_ever_carries_a_move_or_a_position(peers):
    """I-5 on the dialect surface, which builds its messages separately."""
    cop_side, thief_side = peers
    answers = _play(cop_side, thief_side, rounds=6)

    turns = [a["reply_turn"] for a in answers if "reply_turn" in a]
    assert len(turns) >= 6
    for turn in turns:
        assert "move" not in turn
        assert "state" not in turn
        assert len(turn["commit"]) == 64


def test_the_chains_verify_against_the_commitments_that_arrived_live(peers):
    """Rule 36, over a match neither peer played through our own protocol."""
    cop_side, thief_side = peers
    _play(cop_side, thief_side, rounds=6)

    cop = cop_side.handlers.session
    thief = thief_side.handlers.session
    cop_verdict = cop.audit(thief.final_reveal())
    thief_verdict = thief.audit(cop.final_reveal())

    assert cop_verdict["passed"] is True, cop_verdict
    assert thief_verdict["passed"] is True, thief_verdict
    assert cop_verdict["forged_steps"] == []
    assert cop_verdict["withheld_steps"] == []


def test_a_capture_claim_is_answered_truthfully_in_the_response(peers):
    """Rules 21-22. The claim rides in the turn; the answer rides in the reply,
    because the claiming peer must learn the verdict before deciding whether
    there is another turn to take at all."""
    cop_side, thief_side = peers
    answers = _play(cop_side, thief_side, rounds=6)

    responses = [a["claim_response"] for a in answers if a.get("claim_response")]
    assert responses, "a cop that never claims can never capture"
    for response in responses:
        assert set(response) == {"claim", "caught"}
        assert isinstance(response["caught"], bool)


def test_a_turn_for_a_step_we_never_saw_is_refused_not_raised(peers):
    """An exception here reaches the opponent as an opaque transport failure,
    and rule 6 charges both teams for the stall."""
    _, thief_side = peers
    answer = thief_side.submit_turn({"step": 9, "sender": "COP",
                                     "commit": "a" * 64, "hint": "hello"})
    assert answer["ack"] is True  # a first turn at step 9 is odd but legal

    # Now a reveal-shaped turn whose commitment we were never handed: the
    # session refuses it, and the refusal has to come back as an answer.
    session = thief_side.handlers.session
    session.opponent_commitments.clear()
    broken = thief_side.submit_turn({"step": 10, "sender": "COP",
                                     "commit": "", "hint": "x", "nil": False})
    # Three legal shapes, and the point is that all of them are *answers*: we
    # acted, we refused outright, or we declined because acting would have taken
    # a second move in one round (the guard added for gal-roy1's duplicate-step
    # report). A commitment-less turn reads as a handover, so here it is the
    # third. What must never happen is an exception.
    assert ("reply_turn" in broken or broken["ack"] is False
            or broken.get("acted") is False)
    assert broken.get("error") or "reply_turn" in broken


def test_a_repeated_handover_does_not_buy_us_a_second_move(peers):
    """gal-roy1 reported this against us twice before we could reproduce it.

    A nil turn is a handover, so the first one makes us open the round. A
    *second* one, with the opponent still never having acted, must not make us
    act again: that is two of our moves against one of theirs, which is not a
    desynchronisation but a cheat, and a worse outcome than the stall that
    declining risks.

    It is declined rather than raised. An exception crosses MCP as an opaque
    transport failure and rule 6 charges both teams for the stall.
    """
    cop_side, _ = peers
    loop = cop_side.turns(cop_side.handlers.session)

    first = cop_side.submit_turn(nil_turn(constants.ROLE_THIEF))
    assert first["reply_turn"]["step"] == 1
    assert loop.round == 1

    second = cop_side.submit_turn(nil_turn(constants.ROLE_THIEF))
    assert "reply_turn" not in second, "a second handover must not buy a second move"
    assert second["ack"] is True and second["acted"] is False
    assert loop.round == 1, "the declined turn must not advance the round either"


def test_our_step_number_is_monotonic_whatever_arrives(peers):
    """The audit is keyed on the step, so sealing one twice is fatal (rules 19, 36).

    This is the second half of the same report. Even with the handover guarded,
    ``theirs + 1`` can land on a step we have already sealed whenever a peer
    sends a step we are past -- a retry, a duplicate, a driver that numbers
    rounds differently. Two payloads under two commitments at one step number is
    indistinguishable from a forgery, and our own auditor would flag it.

    So this drives deliberately hostile step numbers rather than a tidy sequence.
    """
    cop_side, _ = peers
    session = cop_side.handlers.session

    cop_side.submit_turn(nil_turn(constants.ROLE_THIEF))
    for step in (1, 1, 2, 1, 3, 2):
        answer = cop_side.submit_turn({
            "step": step, "sender": "THIEF", "commit": f"{step:064d}",
            "hint": "somewhere", "scent_grid": {}})
        assert "reply_turn" in answer

    sealed = [record["payload"]["step"] for record in session.final_reveal()
              if record["payload"].get("type") != "system_spec"]
    assert len(sealed) == len(set(sealed)), f"a step was sealed twice: {sealed}"
    assert sealed == sorted(sealed), f"step numbers went backwards: {sealed}"
