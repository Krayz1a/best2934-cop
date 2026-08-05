"""The role rule: who is the cop, in which sub-game, and why it must be derived.

The property under test is not "the roles swap" -- the rule this replaced did
that too. It is that *both peers compute the same assignment*, which the old one
did not: it named the local team first and swapped on parity, so each side made
itself the cop in every odd sub-game and the two disagreed about all six. A
disagreement here is not a bad sub-game, it is an unplayable one, and rule 6
charges both teams for the stall.

So every test below is written from two directions at once wherever it can be.
"""

from __future__ import annotations

import pytest

from p2pchase import constants
from p2pchase.domain import roles


def test_the_lower_group_id_holds_the_cop_for_the_first_half():
    """The rule as gal-roy1 pinned it, at the league's six sub-games."""
    for sub_game in (1, 2, 3):
        assert roles.cop_group("best2934", "gal-roy1", sub_game) == "best2934"
    for sub_game in (4, 5, 6):
        assert roles.cop_group("best2934", "gal-roy1", sub_game) == "gal-roy1"


def test_both_peers_derive_the_same_assignment_from_opposite_sides():
    """The property the parity rule lacked, and the only one that matters.

    One peer holds the pairing as ``(us, them)`` and the other as ``(them, us)``.
    Sorting inside the rule is what makes those the same question.
    """
    for sub_game in range(1, 7):
        ours = roles.role_for("best2934", "gal-roy1", sub_game)
        theirs = roles.role_for("gal-roy1", "best2934", sub_game)
        assert ours == roles.other_role(theirs), (
            f"sub-game {sub_game}: both peers computed {ours!r}")


def test_the_old_parity_rule_would_have_made_us_both_the_cop():
    """A regression pinned to the actual defect, not to its symptom.

    Kept as a test rather than a comment because the failure it describes is
    invisible from one side: a peer running the parity rule is entirely
    self-consistent, and only a second peer disagrees with it.
    """
    def parity_rule(sub_game: int, first: str, second: str) -> str:
        return first if sub_game % 2 == 1 else second

    clashes = [n for n in range(1, 7)
               if parity_rule(n, "best2934", "gal-roy1")
               == parity_rule(n, "gal-roy1", "best2934")]
    assert clashes == [], "sanity: the old rule never agreed with itself"
    assert all(parity_rule(n, "best2934", "gal-roy1") == "best2934"
               for n in (1, 3, 5))


def test_each_team_plays_each_role_three_times():
    """Rule 12 and CONNECT.md section 6: three and three, so the asymmetric
    scoring cannot favour whoever happened to be assigned the cop."""
    mine = [roles.role_for("best2934", "gal-roy1", n) for n in range(1, 7)]
    assert mine.count(constants.ROLE_COP) == 3
    assert mine.count(constants.ROLE_THIEF) == 3


def test_the_halfway_point_follows_the_agreed_series_length():
    """Derived from ``sub_games`` rather than hard-coded at 3.

    The number of sub-games is part of the config both peers fingerprint, so
    deriving the split from it cannot drift from what was agreed. A two-sub-game
    rehearsal swaps after one.
    """
    assert roles.cop_group("a", "b", 1, sub_games=2) == "a"
    assert roles.cop_group("a", "b", 2, sub_games=2) == "b"
    assert roles.cop_group("a", "b", 3, sub_games=6) == "a"


def test_a_team_cannot_be_assigned_roles_against_itself():
    """A one-entry mapping would lose a side silently, much later."""
    with pytest.raises(ValueError, match="playing itself"):
        roles.roles_for_sub_game(1, "best2934", "best2934")


def test_their_spelling_of_a_role_reads_as_ours():
    """gal-roy1's INTEROP.md sends ``COP``/``THIEF``; ours follow the book."""
    assert roles.normalise_role("COP") == constants.ROLE_COP
    assert roles.normalise_role("police") == constants.ROLE_COP
    assert roles.normalise_role("Thief") == constants.ROLE_THIEF
    assert roles.normalise_role("robber") == constants.ROLE_THIEF


def test_a_role_we_cannot_read_is_not_quietly_treated_as_either_one():
    """Defaulting an unknown string onto a role would let a typo pass as a
    legal declaration, which is the clash the check exists to catch."""
    assert roles.normalise_role("sherrif") == ""
    assert roles.normalise_role("") == ""


def test_two_of_the_same_role_is_refused():
    assert "one cop and one thief" in roles.role_clash(
        constants.ROLE_COP, constants.ROLE_COP)


def test_complementary_but_swapped_is_also_refused():
    """The case a complementarity check alone cannot see.

    Both peers are internally consistent and the pairing is playable -- it is
    simply the wrong way round for this sub-game, so the series would be scored
    against the wrong halves.
    """
    clash = roles.role_clash(constants.ROLE_THIEF, constants.ROLE_COP,
                             mine="best2934", opponent="gal-roy1", sub_game=1)
    assert "makes 'best2934' the 'police'" in clash


def test_the_right_way_round_is_accepted():
    assert roles.role_clash(constants.ROLE_COP, constants.ROLE_THIEF,
                            mine="best2934", opponent="gal-roy1", sub_game=1) == ""
    assert roles.role_clash(constants.ROLE_THIEF, constants.ROLE_COP,
                            mine="best2934", opponent="gal-roy1", sub_game=4) == ""


def test_an_undeclared_role_is_accepted_because_it_cannot_be_checked():
    """We report that nothing was checked; we do not invent a verdict."""
    assert roles.role_clash(constants.ROLE_COP, "") == ""


def test_our_own_two_peers_rehearsing_are_not_held_to_the_rule():
    """The rehearsal gate runs both our sides against each other under one group
    id, where the rule genuinely does not apply. Refusing there would break the
    gate that has to pass before every counted game."""
    assert roles.role_clash(constants.ROLE_COP, constants.ROLE_THIEF,
                            mine="best2934", opponent="best2934", sub_game=4) == ""
