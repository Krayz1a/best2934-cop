"""The concession step: a real sealed ``STAY``, not a gesture.

The property under test is that a peer conceding a sub-game stays auditable.
Everything a normal step produces -- a fresh 64-hex commitment, a disclosable
record, a payload that verifies against its nonce -- has to come out of the
terminal step too, because the opponent's auditor does not have a special case
for "they were losing".

The one thing that must *not* come out of it is a move. A brain asked what to
do after the game is decided will answer with a direction, and a direction
claims the game is still running.
"""

from __future__ import annotations

from p2pchase import constants
from p2pchase.domain.crypto import verify
from p2pchase.mcp.reference_v3 import HEX64
from p2pchase.runtime import session_terminal
from p2pchase.runtime.peer_session import PeerSession


def _session(peer_config, role: str = constants.ROLE_THIEF) -> PeerSession:
    return PeerSession(config=peer_config, role=role, game_id="a-vs-b")


def test_the_commitment_is_a_real_sha256_their_validator_would_accept(peer_config):
    commitment = session_terminal.seal_stay(_session(peer_config), 7)
    assert HEX64.match(commitment), "their receive_turn refuses anything else"


def test_the_sealed_move_is_stay_and_never_the_brains_choice(peer_config):
    """A conceding peer must not also claim to have moved somewhere."""
    session = _session(peer_config)
    session_terminal.seal_stay(session, 4)
    decision, _hint, record = session._pending
    assert decision.move == "STAY"
    assert record.payload["move"] == "MOVE:STAY", "their wire encoding of a standstill"
    assert decision.barrier is None


def test_the_record_verifies_against_its_own_nonce(peer_config):
    """The audit runs over this step like any other, so it has to survive it."""
    session = _session(peer_config)
    commitment = session_terminal.seal_stay(session, 9)
    _decision, _hint, record = session._pending
    assert verify(record.payload, record.nonce, commitment)


def test_the_concession_is_recorded_as_truthful(peer_config):
    """Rule 22: the one sentence in a sub-game with nothing to gain by lying."""
    session = _session(peer_config)
    session_terminal.seal_stay(session, 3)
    _decision, _hint, record = session._pending
    assert record.payload["intent"] == constants.INTENT_TRUTH


def test_two_concessions_at_different_steps_seal_different_commitments(peer_config):
    """Equivocation check: one hash must never cover two payloads."""
    first = session_terminal.seal_stay(_session(peer_config), 5)
    second = session_terminal.seal_stay(_session(peer_config), 6)
    assert first != second


def test_the_step_number_is_the_one_asked_for(peer_config):
    session = _session(peer_config)
    session_terminal.seal_stay(session, 12)
    assert session.step == 12
    assert session._pending[2].payload["step"] == 12


def test_the_sealed_position_is_where_we_already_stand(peer_config):
    """STAY settles nowhere new -- and the cop reads this cell at the audit."""
    session = _session(peer_config)
    before = tuple(session.state.position)
    session_terminal.seal_stay(session, 2)
    assert tuple(session._pending[2].payload["state"]) == before


def test_the_step_is_disclosed_even_though_it_was_never_applied(peer_config):
    """The opponent holds a commitment for it, so withholding it reads as concealment."""
    session = _session(peer_config)
    commitment = session_terminal.seal_stay(session, 8)
    assert any(r.get("commit") == commitment for r in session.final_reveal())


def test_applying_it_completes_the_chain_like_any_other_step(peer_config):
    session = _session(peer_config)
    commitment = session_terminal.seal_stay(session, 1)
    session.apply_own_step()
    assert session.records[-1]["commit"] == commitment
    assert session._pending is None


def test_the_hint_is_fixed_rather_than_composed(peer_config):
    """No LLM, no talk engine: a concession must not be able to stall or lie."""
    session = _session(peer_config)
    session_terminal.seal_stay(session, 1)
    assert session._pending[1] == session_terminal.CONCESSION_HINT
    assert session._pending[2].payload["hint"] == session_terminal.CONCESSION_HINT


def test_a_caller_may_override_the_sentence_without_changing_the_move(peer_config):
    session = _session(peer_config)
    session_terminal.seal_stay(session, 1, hint="You have me.")
    assert session._pending[2].payload["hint"] == "You have me."
    assert session._pending[2].payload["move"] == "MOVE:STAY"
