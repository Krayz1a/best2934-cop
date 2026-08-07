"""A new sub-game must reset the board even when nobody sends step 0.

gal-roy1 filed four blockers against us and three of them are this one bug.

We are thief-first: the thief transmits the nil handover at step 0 and the cop
acts first. So a step-0 message reaches us only when *they* are the thief --
that is, only when we are the cop. The session reset was hung off that message,
so ``/cop/mcp`` reset perfectly and ``/thief/mcp`` never reset at all:

    179 -> 214 -> 249 -> 284 -> 319 records, +35 every sub-game

By the time we measured our own endpoint it was at 389, steps 1..389 in one
unbroken session. Their other two blockers follow from it and are not separate
faults: a thief carried to step 300+ of a 35-step horizon has nothing left to do
and plays ``MOVE:STAY`` (they counted 232 of 249), and a thief that has stood
still for hundreds of turns saturates its own trail into a flat plateau with no
gradient to read (six cells pinned at 0.81).

This is the second reset we have hung off a message the opponent does not always
send. The first was ``declare_step0``, which gal-roy1 has never once called.
"""

from __future__ import annotations

import hashlib

from p2pchase import constants
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.mcp.interop import InteropAdapter
from p2pchase.runtime.peer_session import PeerSession

GAME = "best2934-vs-gal-roy1"


def _adapter(peer_config, role=constants.ROLE_THIEF, sub_game=4):
    session = PeerSession(peer_config, role, GAME, sub_game=sub_game, seed=1)
    return InteropAdapter(PeerHandlers(peer_config, session))


def _cop_turn(step: int, sub_game: int = 4) -> dict:
    """A turn the way a cop sends one: a real move, never a step-0 handover.

    ``sub_game`` only varies the sealed commitment, which is the point: a
    genuinely new sub-game seals a new step and cannot reproduce the old
    digest, while a retry resends the one it already sealed. That difference is
    what the adapter reads to tell the two apart.
    """
    return {"step": step, "sender": "COP", "hint": f"closing in {step}",
            "commit": hashlib.sha256(f"sg{sub_game}-turn-{step}".encode()).hexdigest(),
            "scent_grid": {}}


def _records(adapter) -> int:
    return len(adapter.handlers.session.records)


def test_a_cop_opening_at_step_1_starts_a_clean_sub_game(peer_config):
    """The exact sequence that accumulated 389 records on our live thief."""
    adapter = _adapter(peer_config)
    adapter.submit_turn({"step": 0, "sender": "COP", "nil": True})
    for step in (1, 2, 3):
        adapter.submit_turn(_cop_turn(step))
    played = _records(adapter)
    assert played > 1, "the first sub-game did not actually play"

    adapter.submit_turn(_cop_turn(1, sub_game=5))

    assert _records(adapter) == 1, (
        f"a new sub-game opened at step 1 and kept {_records(adapter)} records "
        f"from the last one; this is the +35-per-sub-game leak gal-roy1 measured")


def test_a_step_0_opener_still_resets(peer_config):
    """The path that always worked must keep working -- it is how the cop resets."""
    adapter = _adapter(peer_config, role=constants.ROLE_COP, sub_game=1)
    adapter.submit_turn({"step": 0, "sender": "THIEF", "nil": True})
    for step in (1, 2):
        adapter.submit_turn(_cop_turn(step))

    adapter.submit_turn({"step": 0, "sender": "THIEF", "nil": True})

    assert _records(adapter) == 1


def test_a_resent_step_1_does_not_wipe_a_live_sub_game(peer_config):
    """The risk the fix creates, and the reason step 1 is held to a stricter test.

    A client that retries its opening move must not destroy the board it is
    playing on. The retry resends the commitment it already sealed, so an
    identical digest for a step we already hold is proof of a repeat rather
    than of a new sub-game. Counting rounds cannot make that distinction: the
    nil handover puts our round one ahead of theirs, so we are already past
    round 1 by their first real move.
    """
    adapter = _adapter(peer_config)
    adapter.submit_turn({"step": 0, "sender": "COP", "nil": True})
    adapter.submit_turn(_cop_turn(1))
    before = _records(adapter)

    adapter.submit_turn(_cop_turn(1))

    assert _records(adapter) >= before, "a retried opening move reset a live sub-game"


def test_the_thief_still_moves_after_a_reset(peer_config):
    """Blocker 3 was a symptom, so the reset is what has to cure it."""
    adapter = _adapter(peer_config)
    adapter.submit_turn({"step": 0, "sender": "COP", "nil": True})
    for step in (1, 2, 3):
        adapter.submit_turn(_cop_turn(step))
    adapter.submit_turn(_cop_turn(1, sub_game=5))

    moves = [r["payload"]["move"] for r in adapter.handlers.session.records]
    assert moves and moves[0] != "MOVE:STAY", f"the thief opened with {moves[0]}"
