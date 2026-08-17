"""SPEC 7.2, our half of it.

anrbj666's wire has refused mispaired windows since 2026-08-14 and it never
once fired against us, because we declared no ``sub_game_number`` and silence
cannot mismatch. We now declare one -- and a gate that only works in their
direction is half a gate, so this is ours.

It matters more than it looks. Their turn messages carry no sub-game identifier
at all, and our odd-window walks are byte-identical to one another, so a
mispaired window cannot be attributed after the fact by either team. The
declaration exchanged at negotiate is the only chance anyone gets.
"""

from __future__ import annotations

from p2pchase.runtime import reference_handshake


def test_a_mispaired_window_is_named(peer_config):
    """Our half of 7.2: their gate catches us, ours has to catch them."""
    assert reference_handshake.pairing_mismatch({"sub_game_number": 4}, 5) == 4


def test_agreement_on_the_number_is_not_a_mismatch(peer_config):
    assert reference_handshake.pairing_mismatch({"sub_game_number": 5}, 5) is None


def test_a_peer_that_declares_nothing_is_quiet_and_not_mispaired(peer_config):
    """Silence cannot refuse -- which is why their gate never fired against us.

    Inventing a refusal for a peer that does not implement 7.2 would punish
    them for a requirement the rulebook does not make of them.
    """
    assert reference_handshake.pairing_mismatch({}, 5) is None
    assert reference_handshake.pairing_mismatch({"sub_game_number": "5"}, 5) is None
