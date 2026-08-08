"""The anrbj666 pairing, pinned before the first game rather than after it.

They were absent from the opponents table, so they would have been played on
the defaults: ``first_half`` + ``multiplicative_book_v1``. The scent model
would have been right *by luck* and the convention wrong, and the two
conventions disagree on two of the six sub-games:

    sub-game   odd_even (agreed)   first_half (default)
        2      police              thief        <- both peers play thief
        5      thief               police       <- both peers play cop

Two cops chase nobody, and two thieves are not a game either. It would not have
been caught by the terms comparison -- the role convention is a per-pair term
that lives in the private setup, deliberately outside ``config_sha256`` -- so
the handshake would have agreed on all fourteen values and the series would
have broken on sub-game 2.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from p2pchase.domain import roles

REPO = Path(__file__).resolve().parents[3]
OPPONENT = "anrbj666"
MINE = "best2934"


def _setup(role: str) -> dict:
    return json.loads((REPO / "config" / role / "setup.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("role", ["police", "thief"])
def test_anrbj666_is_in_the_opponents_table_at_all(role):
    """Absence is the bug. A default that happens to fit is not a declaration."""
    assert OPPONENT in _setup(role)["opponents"], (
        "anrbj666 would fall through to the first_half default")


@pytest.mark.parametrize("role", ["police", "thief"])
def test_the_agreed_pairing_terms_are_written_out(role):
    pairing = _setup(role)["opponents"][OPPONENT]
    assert pairing["role_convention"] == "odd_even"
    assert pairing["scent_model"] == "multiplicative_book_v1"
    assert pairing["tie_rule"] == "series_add"


def test_our_roles_match_what_anrbj666_stated():
    """They said: "we sort first, so anrbj666 cop on 1/3/5". Derived, not assumed."""
    ours = {n: roles.role_for(MINE, OPPONENT, n, convention="odd_even")
            for n in range(1, 7)}
    assert ours == {1: "thief", 2: "police", 3: "thief",
                    4: "police", 5: "thief", 6: "police"}


def test_the_default_convention_would_have_clashed_on_two_sub_games():
    """The regression stated as the sub-games it breaks, not as a description."""
    clashes = [n for n in range(1, 7)
               if roles.role_for(MINE, OPPONENT, n, convention="odd_even")
               != roles.role_for(MINE, OPPONENT, n, convention="first_half")]
    assert clashes == [2, 5]
