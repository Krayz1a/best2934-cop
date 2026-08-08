"""Our cop must play a thief that opens at step 1 with a real move.

imreeyal asked this directly and it decides sub-games 1/3/5, where we are the
cop. The two conventions were never agreed and we assumed rather than asked:

    ours:   thief -> step 0 nil handover     cop moves at step 1
    theirs: thief -> step 1 WITH an action   cop replies at step 2

Their thief transmits no nil handover and no ``declare_step0`` on the wire at
all -- their step-0 record exists, but it is sealed into the audit payload and
never sent. So if our cop required the handover before it would accept a turn,
we would refuse them three times per series and take three technical losses
under rule 6, on a disagreement neither side had written down.

They found and fixed the mirror of this on their side (M7-53): our step-0 frame
used to match no branch of their sequencer, fall through to ILLEGAL and collapse
the sub-game on every window where they play cop. Half a series, before a move.
Answered here by test rather than by inspection, because "I read the code and it
looks fine" is what produced the disagreement in the first place.
"""

from __future__ import annotations

import hashlib

from p2pchase import constants
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.mcp.interop import InteropAdapter
from p2pchase.runtime.peer_session import PeerSession

GAME = "best2934-vs-imreeyal"


def _our_cop(peer_config, sub_game: int = 1) -> InteropAdapter:
    """Us as the cop on an odd sub-game, freshly started, nothing received."""
    session = PeerSession(peer_config, constants.ROLE_COP, GAME, sub_game=sub_game, seed=1)
    return InteropAdapter(PeerHandlers(peer_config, session))


def _their_opening_move(step: int = 1, sub_game: int = 1) -> dict:
    """imreeyal's opening frame: step 1, a real action, no handover before it."""
    return {"step": step, "sender": "THIEF", "hint": "somewhere near the water",
            "commit": hashlib.sha256(f"imreeyal-sg{sub_game}-{step}".encode()).hexdigest(),
            "scent_grid": {}}


def test_our_cop_accepts_a_thief_that_opens_at_step_1_with_an_action(peer_config):
    """The answer to imreeyal's question, as an assertion rather than a promise."""
    answer = _our_cop(peer_config).submit_turn(_their_opening_move())

    assert answer.get("ack") is True, f"our cop refused their opening move: {answer}"
    assert "error" not in answer


def test_our_cop_replies_with_its_own_move_rather_than_a_bare_acknowledgement(peer_config):
    """Accepting the frame is not enough -- the round has to come home.

    Their sequencer expects our move to ride back in the same call (I-7). An
    ``ack`` with no ``reply_turn`` would stall the sub-game just as completely
    as a refusal, and would be harder for either of us to diagnose.
    """
    answer = _our_cop(peer_config).submit_turn(_their_opening_move())

    reply = answer.get("reply_turn")
    assert reply, f"no reply turn came home: {answer}"
    assert reply.get("commit"), "our reply must carry a sealed commitment"


def test_our_reply_shares_their_step_number_because_a_step_is_a_whole_round(peer_config):
    """Pinning the divergence this test found, which neither side had named.

    We answer their step 1 **at step 1**, not at step 2. That is deliberate: in
    our model a step is one round -- one action from each side -- so both peers
    carry the same step number through a round and advance together. Our own
    logs run steps 1..35 with 35 records in each peer's chain, so ``max_steps:
    35`` means *35 moves each*.

    imreeyal described their wire as ``thief -> step 1 ... cop replies step 2``,
    which numbers each *action*. If that is literal rather than shorthand, the
    same signed ``max_steps: 35`` buys 35 moves each on our side and about 17
    each on theirs -- and the side that reads it the long way expects a chase
    that the other has already ended in a survival.

    This is the failure the fourteen-term comparison cannot catch: every value
    is equal and one of them does not mean the same thing. Raised with them
    rather than patched here, because we do not know yet which of us moves.
    """
    answer = _our_cop(peer_config).submit_turn(_their_opening_move(step=1))

    assert int(answer["reply_turn"]["step"]) == 1, (
        "a step is a round on our side; if this changes, imreeyal must be told")


def test_the_opening_move_is_recorded_and_the_session_is_not_empty(peer_config):
    """Their step 1 must land in our chain, or the final audit cannot verify it."""
    adapter = _our_cop(peer_config)
    adapter.submit_turn(_their_opening_move())

    assert adapter.handlers.session.records, "their opening move was not recorded"


def test_we_still_accept_the_nil_handover_we_send_ourselves(peer_config):
    """The tolerance is additive: gal-roy1 opens with the nil turn at step 0.

    Two opponents, two conventions, and we travel to both rather than asking
    either to move. A fix for imreeyal that broke the step-0 opener would trade
    one blocked pairing for another.
    """
    answer = _our_cop(peer_config, sub_game=1).submit_turn(
        {"step": 0, "sender": "THIEF", "nil": True})

    assert answer.get("ack") is not False, f"the nil handover stopped working: {answer}"


def test_an_opening_action_at_step_1_does_not_consume_a_second_move(peer_config):
    """One inbound frame, one outbound move. Not two.

    imreeyal's M7-53 absorbs our step-0 frame *and advances nothing*, so our
    first real move still lands as step 1. The symmetric hazard on our side is
    treating their step-1 action as both an opener and a turn, and answering
    twice -- which is a cheat in our favour and would void the series.
    """
    adapter = _our_cop(peer_config)
    answer = adapter.submit_turn(_their_opening_move())

    ours = [r for r in adapter.handlers.session.records
            if str(r.get("role", "")).lower() in {constants.ROLE_COP, "cop", "police"}]
    assert len(ours) <= 1, f"we took more than one move for one inbound turn: {ours}"
    assert answer.get("ack") is True
