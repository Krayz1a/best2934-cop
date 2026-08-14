"""Rule 47 over the network: a thief with no way out has lost (rules 35, 47).

``OwnState.thief_is_boxed_in`` has existed since the first week. It was checked
in the local rehearsal, and in the live GUI, and on neither networked wire --
so the rule fired where nobody was watching and never where the points are.

imreeyal found it on 2026-08-14 from our own disclosed records. In all three of
our thief sub-games the picture is identical:

    our thief's cell   (6, 6) -- the corner, by step 6
    their barriers     (5, 6) and (6, 5) -- both exits, by step 7
    our thief after    STAY x30, then win_claim {"type": "survival"}

Thirty sealed records of standing still on a board our own engine could see was
closed, and then a claim of survival at the end of each one. Under rule 47 those
are three captures: the series was 90-30 to them, not the 47-47 both engines
settled on.

The survival claim is what makes this rule 35 rather than merely a lost game.
Two reports naming different outcomes for one sub-game void the match for both
teams -- so the fix is not only to stop playing when boxed, but to stop
*claiming* the opposite of what our own board says.

The last test is the narrow one, and it is the reason this is not simply "concede
when a wall is near": a thief with one exit left is not captured, and conceding
there would file a capture the opponent never recorded.
"""

from __future__ import annotations

import pytest

from p2pchase import constants
from p2pchase.runtime import session_terminal, wall_capture
from p2pchase.runtime.peer_session import PeerSession
from p2pchase.runtime.turn_loop import TurnLoop

#: The corner our thief ran to, and the two cells imreeyal sealed behind it.
CORNER = (6, 6)
THEIR_WALLS = ((5, 6), (6, 5))


@pytest.fixture
def thief(thief_config) -> PeerSession:
    return PeerSession(thief_config, constants.ROLE_THIEF, "g", seed=6)


@pytest.fixture
def cop(peer_config) -> PeerSession:
    return PeerSession(peer_config, constants.ROLE_COP, "g", seed=6)


def corner_thief(session: PeerSession, walls=THEIR_WALLS) -> PeerSession:
    """Put the session exactly where the friendly's sub-games 2, 4 and 6 were."""
    session.state.position = CORNER
    for wall in walls:
        session.state.board.barriers.add(wall)
    return session


def turn(step: int, **extra) -> dict:
    """An inbound turn in the shape ``parse_turn`` reads off either wire."""
    return {"step": step, "sender": "POLICE", "commit": "c" * 64,
            "hint": "sealed", "scent_grid": {}, **extra}


# ------------------------------------------------------------------ the rule
def test_a_thief_with_both_exits_sealed_is_captured(thief):
    assert wall_capture.boxed_in(corner_thief(thief)) is True
    assert thief.i_am_caught is True


def test_a_thief_with_one_exit_left_is_not(thief):
    """The narrow reading. One way out is a thief still in the game, and
    conceding here would file a capture the opponent has not recorded -- the
    rule 35 disagreement from the other direction."""
    assert wall_capture.boxed_in(corner_thief(thief, walls=THEIR_WALLS[:1])) is False
    assert thief.i_am_caught is False


def test_standing_still_is_not_an_escape(thief):
    """``STAY`` is always legal, so reading rule 47 literally would make it
    unsatisfiable. Both engines read it as no legal *movement*, which is the
    spelling imreeyal asked for in the pairing terms."""
    corner_thief(thief)

    assert "STAY" in thief.state.board.legal_moves(CORNER)
    assert wall_capture.boxed_in(thief) is True


def test_the_cop_is_never_boxed_in(cop):
    """A cop that walled itself in has made a mistake, not lost the sub-game.
    Rule 47 names the thief."""
    cop.state.position = CORNER
    for wall in THEIR_WALLS:
        cop.state.board.barriers.add(wall)

    assert wall_capture.boxed_in(cop) is False


# ------------------------------------------------------------- on the wire
def test_the_barrier_that_closes_the_last_exit_ends_the_sub_game(thief):
    """The wiring that was missing. Their wall lands, and the sub-game is over
    at that moment -- not twenty-eight rounds later at the move ceiling."""
    corner_thief(thief, walls=THEIR_WALLS[:1])
    loop = TurnLoop(thief)

    loop.absorb(turn(7, barrier_placed=list(THEIR_WALLS[1])))

    assert loop.finished == constants.OUTCOME_CAPTURE


def test_a_boxed_thief_does_not_claim_survival_at_the_threshold(thief):
    """The rule 35 half, and the one that cost us the friendly.

    Reaching step 35 is necessary and it is not sufficient. A thief boxed since
    step 7 also reaches step 35, and claiming survival there contradicts our own
    signed record of thirty stationary steps.
    """
    corner_thief(thief)
    thief.state.step = thief.state.survival_threshold
    loop = TurnLoop(thief)

    message = loop.take_turn(36)

    assert message.get("win_claim") is None
    assert loop.finished == constants.OUTCOME_CAPTURE


def test_an_unboxed_thief_still_claims_its_survival(thief):
    """The other half, and the one that protects every game we actually win."""
    reached = thief.state.step = thief.state.survival_threshold
    loop = TurnLoop(thief)

    message = loop.take_turn(36)

    assert message["win_claim"] == {"type": "survival", "steps": reached}
    assert loop.finished == constants.OUTCOME_SURVIVAL


def test_the_outcome_reads_capture_even_if_no_round_noticed(thief):
    """The last-resort reading, for a sub-game that ended by a dropped
    connection or a watchdog rather than by a round of the loop. The board is
    still ours to read."""
    corner_thief(thief)
    thief.state.step = thief.state.survival_threshold

    assert TurnLoop(thief).outcome() == constants.OUTCOME_CAPTURE


def test_the_terminal_message_concedes_rather_than_signing_off(thief):
    """reference-v3's last message is sealed and disclosed, so a boxed thief
    signing ``CLOSING_HINT`` there hands the auditor a contradiction with its
    own board."""
    corner_thief(thief)
    thief.state.step = thief.state.survival_threshold
    loop = TurnLoop(thief)

    message = session_terminal.build_terminal(thief, loop, "THIEF", 36, None)

    assert message.get("win_claim") is None
    assert message["hint"] == session_terminal.CONCESSION_HINT
