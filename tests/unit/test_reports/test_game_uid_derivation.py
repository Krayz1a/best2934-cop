"""The match uid is derived by both peers, never rolled by one of them.

``game_uid`` is what joins the four artifacts of one match, across two
independently written codebases. If the two sides carry different uids, the
lecturer receives two matches that cannot be joined -- from two teams who both
played correctly and both reported honestly.

We shipped ``uuid.uuid4()`` until 2026-08-14. The friendly against imreeyal is
what exposed it: two reports describing the same six sub-games, built from
identical terms, carrying

    ours    f8e9733a-7665-4044-a392-69640a28ac64
    theirs  0d98626a-7369-b854-e473-3df1898d45f1

Theirs is not a version-4 uuid at all -- the version nibble is ``b`` -- which
is the tell that one side derived while the other rolled a die.

anrbj666 stated the cost exactly on league issue #49: a uid mismatch found
before play is a five-minute fix; found at settlement it voids the match for
both teams under rule 35.
"""

from __future__ import annotations

from p2pchase.domain.core_terms import core_terms
from p2pchase.reports.naming import derive_game_uid, new_game_uid

#: `vectors/game_uid.json` from copthief-league-protocol, status CORE.
#: Inlined so the suite stays hermetic without a clone of that repo.
KIT_TERMS = {
    "board_size": 7, "smell_grid_size": 5, "decay_per_step": 0.1,
    "emit_intensity": 0.9, "min_center_intensity": 0.5, "max_steps": 35,
    "barriers_max": 14, "setting": "Haifa", "hint_max_words": 15,
    "axis_origin_corner": "top-left", "axis_start_index": 0,
    "thief_start": [3, 3], "cop_start": [0, 0], "num_games": 1,
}
KIT_UID = "1e73c318-5b29-4a7b-1c60-ecb8286265f0"

#: What imreeyal's report actually carried for our 2026-08-14 friendly. This is
#: a live cross-implementation value, not a fixture: they computed it, mailed
#: it, and we reproduce it here from our own config.
IMREEYAL_FRIENDLY_UID = "0d98626a-7369-b854-e473-3df1898d45f1"


def test_the_kit_vector_reproduces():
    assert derive_game_uid(KIT_TERMS, "team-aleph", "team-bet") == KIT_UID


def test_the_pair_is_sorted_so_neither_side_has_to_be_told_who_is_first():
    """Order independence is the whole reason there is no round-trip."""
    assert derive_game_uid(KIT_TERMS, "team-bet", "team-aleph") == KIT_UID


def test_our_config_reproduces_the_uid_imreeyal_mailed_us(peer_config):
    """The cross-implementation check, on bytes another team produced.

    This is the assertion that would have failed yesterday, and the one that
    proves the fix against something other than our own opinion.
    """
    uid = derive_game_uid(core_terms(peer_config.shared), "best2934", "imreeyal")

    assert uid == IMREEYAL_FRIENDLY_UID


def test_a_derived_uid_is_not_a_version_four_uuid(peer_config):
    """The tell that separated the two implementations, pinned deliberately.

    A derived uid takes its version nibble from the hash, so it is almost never
    ``4``. Asserting this keeps anyone from "fixing" a future mismatch by
    reaching for ``uuid4()`` again because the value looked wrong.
    """
    uid = derive_game_uid(core_terms(peer_config.shared), "best2934", "imreeyal")

    assert uid[14] != "4", "a v4 uuid here means somebody rolled it"
    assert new_game_uid()[14] == "4", "and the random path still is one"


def test_different_terms_give_a_different_uid():
    """It has to be sensitive to the terms, or it certifies nothing."""
    moved = {**KIT_TERMS, "max_steps": 36}

    assert derive_game_uid(moved, "team-aleph", "team-bet") != KIT_UID


def test_different_opponents_give_a_different_uid():
    assert derive_game_uid(KIT_TERMS, "team-aleph", "team-gimel") != KIT_UID
