"""Which team plays which role in which sub-game (agreed with gal-roy1).

The rulebook never assigns roles across a series, and the scoring is asymmetric
-- capture pays the cop 20, survival pays the thief 10 -- so a pairing where one
team always played cop would be structurally unfair. We proposed 3 and 3 in
CONNECT.md section 6; gal-roy1 pinned the exact form, and this module is that
agreement:

    the cop for the first half of the series is ``sorted(group_ids)[0]``,
    and for the second half the other team.

Sorting is the whole point. It makes the assignment *derivable* rather than
negotiable: both peers compute the same answer from the two group ids and the
sub-game number alone, with no message to exchange and nothing to disagree about
mid-series. That matters because a role clash is not a bad sub-game, it is an
unplayable one -- two cops chase nobody -- and rule 6 charges *both* teams for
the stall.

The rule this replaces looked equivalent and was not. It swapped on the parity
of the sub-game number with the *local* team named first, so each peer computed
itself as the cop in every odd sub-game and the two sides disagreed about all
six. Nothing caught it because only one side ever ran it: the local harness
plays both halves from one process, where a self-consistent wrong answer is
indistinguishable from a right one.
"""

from __future__ import annotations

from .. import constants

#: The two role conventions in use across the league, both of which give each
#: team three sub-games of each role and both of which are order-independent.
#:
#: ``first_half`` is the one gal-roy1 pinned and the one this module shipped
#: alone. ``odd_even`` is the form published in the copthief-league-protocol kit
#: and the one imreeyal, anrbj666 and uoh-sqak already play. Neither is more
#: correct -- the rulebook assigns no roles at all -- so the convention is a
#: *per-pairing* term like the scent model, not a league constant, and it lives
#: in the private setup file keyed by opponent.
#:
#: Both peers must hold the same one. Under either, a peer that computes its own
#: answer honestly and differently from its opponent produces two cops, and rule
#: 6 charges both teams for the sub-game that cannot start.
FIRST_HALF = "first_half"
ODD_EVEN = "odd_even"
ROLE_CONVENTIONS = (FIRST_HALF, ODD_EVEN)
DEFAULT_CONVENTION = FIRST_HALF

#: Every spelling of a role we might be handed. Ours follow the book's Hebrew;
#: gal-roy1's INTEROP.md sends ``"COP"`` and ``"THIEF"``. A role we cannot read
#: is not silently treated as either one -- see :func:`normalise_role`.
ROLE_SPELLINGS = {
    "police": constants.ROLE_COP, "cop": constants.ROLE_COP,
    "thief": constants.ROLE_THIEF, "robber": constants.ROLE_THIEF,
}


def normalise_role(role: str) -> str:
    """Their spelling of a role, in ours. ``""`` when it is neither.

    Unrecognised is deliberately not a default. Mapping an unknown string onto
    one of the two roles would let a typo pass as a legal declaration, and the
    clash it hides is exactly what :func:`role_clash` exists to catch.
    """
    return ROLE_SPELLINGS.get(str(role).strip().lower(), "")


def other_role(role: str) -> str:
    """The role the opponent must hold if ours is ``role``."""
    return constants.ROLE_THIEF if role == constants.ROLE_COP else constants.ROLE_COP


def cop_group(group_a: str, group_b: str, sub_game: int,
              sub_games: int = constants.NUM_SUB_GAMES,
              convention: str = DEFAULT_CONVENTION) -> str:
    """Which of the two teams plays the cop in this sub-game.

    Order-independent by construction under *either* convention: the arguments
    are sorted before anything is decided, so a peer holding the pairing as
    ``(us, them)`` and a peer holding it as ``(them, us)`` reach the same
    answer. That is the property the old parity rule lacked.

    Under ``first_half`` the halfway point is derived from ``sub_games`` rather
    than hard-coded at 3, because the number of sub-games is part of the config
    both peers fingerprint -- so deriving it cannot drift from what was agreed.
    An odd series cannot be split evenly and the extra sub-game falls to the
    second-sorted team; that is arbitrary, but it is arbitrary *identically on
    both sides*, which is the only property that actually matters here.

    An unknown convention raises rather than falling back to either one. A
    silent fallback is how two peers end up internally consistent and mutually
    unplayable, which is the whole failure this module exists to prevent.
    """
    first, second = sorted((str(group_a), str(group_b)))
    if convention == ODD_EVEN:
        return first if int(sub_game) % 2 == 1 else second
    if convention == FIRST_HALF:
        return first if int(sub_game) <= int(sub_games) // 2 else second
    raise ValueError(f"unknown role convention {convention!r}; "
                     f"expected one of {ROLE_CONVENTIONS}")


def convention_divergence(group_a: str, group_b: str,
                          left: str = FIRST_HALF, right: str = ODD_EVEN,
                          sub_games: int = constants.NUM_SUB_GAMES) -> list[int]:
    """The sub-games on which two conventions disagree about who is the cop.

    Computed rather than reasoned about, because we got it wrong by hand. We
    told imreeyal the two conventions diverged at sub-games 2, 4 and 5; the
    answer is 2 and 5, and they corrected us from our own published lists.
    Sub-game 4 is the second-sorted team's cop under both rules.

    The mistake is worth a function rather than a fix. Both conventions agree on
    *four* of six sub-games -- including sub-game 1, the one a pairing is most
    likely to test -- so a mismatch does not announce itself. It plays cleanly,
    twice, and then produces two cops in sub-game 2.
    """
    return [n for n in range(1, int(sub_games) + 1)
            if cop_group(group_a, group_b, n, sub_games, left)
            != cop_group(group_a, group_b, n, sub_games, right)]


def role_for(mine: str, theirs: str, sub_game: int,
             sub_games: int = constants.NUM_SUB_GAMES,
             convention: str = DEFAULT_CONVENTION) -> str:
    """The role *we* hold in this sub-game, given who we are playing."""
    return (constants.ROLE_COP
            if cop_group(mine, theirs, sub_game, sub_games, convention) == str(mine)
            else constants.ROLE_THIEF)


def roles_for_sub_game(sub_game: int, group_a: str, group_b: str,
                       sub_games: int = constants.NUM_SUB_GAMES,
                       convention: str = DEFAULT_CONVENTION) -> dict[str, str]:
    """Group id -> role for one sub-game.

    Refuses two identical group ids rather than returning a one-entry dict that
    silently loses a side. A team cannot play itself over the protocol -- the
    rule is a tie-break *between* two teams and has nothing to say about one --
    and a collapsed mapping would surface much later as a missing role.
    """
    if str(group_a) == str(group_b):
        raise ValueError(f"both sides are {group_a!r}: roles are undefined for a team "
                         f"playing itself")
    cop = cop_group(group_a, group_b, sub_game, sub_games, convention)
    return {str(group_a): constants.ROLE_COP if str(group_a) == cop else constants.ROLE_THIEF,
            str(group_b): constants.ROLE_COP if str(group_b) == cop else constants.ROLE_THIEF}


def role_clash(ours: str, theirs: str, mine: str = "", opponent: str = "",
               sub_game: int = 1,
               sub_games: int = constants.NUM_SUB_GAMES,
               convention: str = DEFAULT_CONVENTION) -> str:
    """Why these two roles cannot play each other, or ``""`` if they can.

    Two checks, and the first one holds even when we do not know who we are
    playing. *Complementary*: one cop and one thief, because two of either is
    not a game. *Correct*: the pair matches what the agreed rule derives for this
    sub-game, which catches the case where both peers are internally consistent
    and have simply swapped the series -- complementary, playable, and scored
    against the wrong halves.

    The second check is skipped when the group ids are unknown or equal. Equal
    means a rehearsal of our own two peers against each other, where the rule
    genuinely does not apply; refusing there would break the gate that has to
    pass before every counted game.
    """
    if not theirs:
        return ""  # nothing declared, so nothing to check -- reported, not assumed
    if theirs == ours:
        return f"both peers declared {ours!r}; one cop and one thief or there is no game"
    if not mine or not opponent or str(mine) == str(opponent):
        return ""
    expected = role_for(str(mine), str(opponent), sub_game, sub_games, convention)
    if expected != ours:
        return (f"sub-game {sub_game} makes {mine!r} the {expected!r} under the {convention!r} "
                f"convention agreed with {opponent!r}, but we are playing {ours!r}")
    return ""
