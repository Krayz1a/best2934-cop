"""Non-game records are excused by TYPE, not by step number.

Handed to us by imreeyal on league issue #45, out of their own audit log:
uoh-sqak seals ``control`` records *inside* the game step space, so their
disclosed steps read ``[1, 2, 1, 2, 3, ... 35]`` and every audit between two
honest peers failed. Their auditor called it a continuity break.

Ours called it **forgery**. A control record numbered 1 carries a different
commitment from the turn we were handed at step 1, so the cross-check reported
``forged: [1]`` -- the single verdict in this codebase that cannot be walked
back, levelled at a peer who did nothing wrong. Reproduced before it was fixed;
these tests are what stops it coming back.

The other half of every test here is that the exclusion is not a way out. A
non-game record does not count as its step having been disclosed, so a move
relabelled ``control`` is withheld rather than excused.
"""

from __future__ import annotations

from p2pchase.domain.audit import audit_against_commitments, is_game_record
from p2pchase.domain.crypto import commit

TURNS = {n: commit({"step": n, "move": f"MOVE:N{n}"}) for n in (1, 2, 3)}
RECEIVED = {n: record.commit for n, record in TURNS.items()}


def _turn(step: int) -> dict[str, object]:
    return TURNS[step].audit_view()


def _sealed(payload: dict[str, object]) -> dict[str, object]:
    return commit(payload).audit_view()


# ------------------------------------------------------- honest peers pass
def test_a_control_record_inside_the_game_step_space_is_not_forgery():
    """uoh-sqak's real shape, and the verdict that must never be `forged`."""
    verdict = audit_against_commitments(
        [_turn(1), _turn(2), _sealed({"step": 1, "type": "control", "note": "ping"}),
         _turn(3)], RECEIVED)
    assert verdict.passed
    assert verdict.forged_steps == []


def test_the_interleaved_chain_verifies_every_record_it_holds():
    """Excused from the cross-check, still checked against its own seal."""
    verdict = audit_against_commitments(
        [_turn(1), _sealed({"step": 1, "type": "control"}), _turn(2), _turn(3)], RECEIVED)
    assert verdict.verified_steps == 4


def test_our_own_step_zero_declaration_still_passes():
    verdict = audit_against_commitments(
        [_sealed({"step": 0, "type": "system_spec", "spec": {}}),
         _turn(1), _turn(2), _turn(3)], RECEIVED)
    assert verdict.passed


def test_a_negative_step_is_excused_even_untyped():
    """uoh-sqak's durable fix, which has to work for peers we have not met."""
    verdict = audit_against_commitments(
        [_sealed({"step": -1, "note": "no type field at all"}),
         _turn(1), _turn(2), _turn(3)], RECEIVED)
    assert verdict.passed


def test_every_type_the_league_seals_is_recognised():
    for kind in ("system_spec", "step_zero", "control", "equivocation"):
        assert not is_game_record({"payload": {"step": 1, "type": kind}}, 1)


def test_a_tampered_non_game_record_still_fails():
    """Excused from the cross-check is not excused from arithmetic."""
    record = _sealed({"step": 1, "type": "control"})
    record["payload"] = {"step": 1, "type": "control", "note": "added afterwards"}
    assert not audit_against_commitments([record, _turn(1), _turn(2), _turn(3)],
                                         RECEIVED).passed


# ------------------------------------------------------------ cheats fail
def test_a_move_relabelled_control_is_withheld_rather_than_excused():
    """The loophole the exclusion would open if it also marked the step seen."""
    verdict = audit_against_commitments(
        [_turn(1), _sealed({"step": 2, "type": "control", "move": "MOVE:S2"}), _turn(3)],
        RECEIVED)
    assert not verdict.passed
    assert verdict.withheld_steps == [2]


def test_a_plainly_rewritten_move_is_still_forgery():
    """The check this fix must not weaken."""
    verdict = audit_against_commitments(
        [_turn(1), _sealed({"step": 2, "move": "MOVE:S2"}), _turn(3)], RECEIVED)
    assert verdict.forged_steps == [2]


def test_an_omitted_move_is_still_withheld_when_a_control_shares_its_number():
    """Two records at step 2, neither of them the move we hold a seal for."""
    verdict = audit_against_commitments(
        [_turn(1), _sealed({"step": 2, "type": "control"}), _turn(3)], RECEIVED)
    assert verdict.withheld_steps == [2]


def test_a_real_move_is_a_game_record():
    assert is_game_record({"payload": {"step": 1, "move": "MOVE:N"}}, 1)


def test_an_unknown_type_inside_the_step_space_is_treated_as_a_move():
    """We do not let a peer invent a type to opt out of the cross-check."""
    assert is_game_record({"payload": {"step": 1, "type": "whatever"}}, 1)
