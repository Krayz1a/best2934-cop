"""The receiving half of the deception channel.

These tests pin down what a sentence is allowed to mean. The decoder is the
only reason lying costs the liar anything, so its failure modes matter: it must
refuse to guess (a wrong guess punishes an honest opponent) and it must refuse
to be silenced (an opponent that writes vaguer sentences must not be able to
freeze our trust estimator at its current value).
"""

from __future__ import annotations

import pytest

from p2pchase.strategy.hint_decoder import heading_from_hint, opposite


@pytest.mark.parametrize(
    ("hint", "expected"),
    [
        ("I am heading north past Harlem", "N"),
        ("Running SOUTH, catch me if you can", "S"),
        ("east of the bridge and gone", "E"),
        ("west, always west", "W"),
        ("going nowhere, I like it here", "STAY"),
    ],
)
def test_a_compass_word_anywhere_in_the_sentence_is_found(hint, expected):
    assert heading_from_hint(hint) == expected


@pytest.mark.parametrize("hint", ["", "catch me if you can", "somewhere around here"])
def test_a_sentence_naming_no_direction_claims_nothing(hint):
    """Uninformative is not the same as dishonest, so it must not score."""
    assert heading_from_hint(hint) is None


@pytest.mark.parametrize("hint", ["north-east bound", "heading northeast", "south west now"])
def test_a_compound_bearing_is_refused_rather_than_guessed(hint):
    """"North-east" is consistent with two legal moves. Scoring it as either
    would convict an honest opponent half the time."""
    assert heading_from_hint(hint) is None


def test_the_first_direction_wins_when_a_sentence_names_two():
    """A sentence is read left to right, as a reader would read it."""
    assert heading_from_hint("north then west") == "N"


def test_a_liar_names_the_reverse_of_the_heading_it_took():
    assert opposite("N") == "S"
    assert opposite("S") == "N"
    assert opposite("E") == "W"
    assert opposite("W") == "E"


def test_standing_still_has_no_reverse_to_name():
    """There is no misdirection available when you did not move."""
    assert opposite("STAY") == "STAY"
