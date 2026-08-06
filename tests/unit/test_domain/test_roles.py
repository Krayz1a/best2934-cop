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


# --------------------------------------------------------------------------
# The second convention. Both give each team three sub-games of each role, both
# are order-independent, and they are not the same rule.
# --------------------------------------------------------------------------

def test_the_odd_even_convention_gives_the_lower_group_id_the_odd_sub_games():
    """The kit's published form, which imreeyal, anrbj666 and uoh-sqak play."""
    for sub_game in (1, 3, 5):
        assert roles.cop_group("best2934", "imreeyal", sub_game, convention=roles.ODD_EVEN) \
            == "best2934"
    for sub_game in (2, 4, 6):
        assert roles.cop_group("best2934", "imreeyal", sub_game, convention=roles.ODD_EVEN) \
            == "imreeyal"


def test_odd_even_is_order_independent_too():
    """The property that makes a convention usable at all: two peers holding the
    pairing in opposite order must not need a message to agree."""
    for sub_game in range(1, 7):
        assert (roles.cop_group("best2934", "imreeyal", sub_game, convention=roles.ODD_EVEN)
                == roles.cop_group("imreeyal", "best2934", sub_game, convention=roles.ODD_EVEN))


def test_the_two_conventions_diverge_at_sub_games_two_and_five():
    """The count we got wrong by hand, which is why it is computed here.

    We told imreeyal the conventions disagreed at sub-games 2, 4 and 5. They
    disagree at 2 and 5 -- sub-game 4 belongs to the second-sorted team under
    both rules -- and imreeyal corrected us from our own published lists.
    """
    assert roles.convention_divergence("best2934", "imreeyal") == [2, 5]


def test_the_conventions_agree_on_sub_game_one_which_is_what_makes_it_dangerous():
    """Four of six sub-games agree, including the first.

    A pairing that tests the handshake on sub-game 1 and calls the convention
    settled has learned nothing. The mismatch waits until sub-game 2 and then
    produces two cops -- and by then the series is under way.
    """
    agree = [n for n in range(1, 7) if n not in roles.convention_divergence("best2934", "imreeyal")]
    assert agree == [1, 3, 4, 6]


def test_each_convention_still_splits_the_series_evenly():
    """Neither team may keep the easier half (rule 12b). Capture pays the cop 20
    and survival pays the thief 10, so 3/3 is the fairness property, and it has
    to hold under *both* rules rather than only the one we shipped first."""
    for convention in roles.ROLE_CONVENTIONS:
        cops = [roles.cop_group("best2934", "imreeyal", n, convention=convention)
                for n in range(1, 7)]
        assert cops.count("best2934") == cops.count("imreeyal") == 3


def test_an_unknown_convention_raises_rather_than_picking_one():
    """A silent fallback is how two peers end up internally consistent and
    mutually unplayable -- the exact failure this module was rewritten to stop."""
    with pytest.raises(ValueError, match="unknown role convention"):
        roles.cop_group("best2934", "imreeyal", 1, convention="alternating")


def test_a_clash_report_names_the_convention_it_judged_against():
    """Two teams can each be right under their own rule. A message that says
    only "you should be the thief" starts an argument; one that says which
    convention produced that answer ends it."""
    # Complementary on purpose: one cop, one thief, so this is the *playable*
    # clash that gets past the first check and is caught only by the rule --
    # two peers that have swapped the series and would score it wrong.
    complaint = roles.role_clash(
        constants.ROLE_COP, constants.ROLE_THIEF, "best2934", "imreeyal",
        sub_game=2, convention=roles.ODD_EVEN)
    assert complaint, "sub-game 2 makes imreeyal the cop under odd_even"
    assert "odd_even" in complaint and "imreeyal" in complaint

    # And the same pairing is fine under the convention we hold with gal-roy1,
    # which is the whole reason the convention travels with the opponent.
    assert not roles.role_clash(constants.ROLE_COP, constants.ROLE_THIEF,
                                "best2934", "imreeyal", sub_game=2,
                                convention=roles.FIRST_HALF)
