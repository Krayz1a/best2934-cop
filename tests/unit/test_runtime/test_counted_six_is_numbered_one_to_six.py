"""A throwaway before the counted series must not push the six off 1..6.

gal-roy1's agreed order for 2026-08-17 is one alignment throwaway on sub-game 2,
then the counted six, in a single serving process. Their driver declares
``sub_game_number`` at ``declare_step0`` and omits it from the opening
``submit_turn`` -- verified on the wire on 2026-08-16, where our counter read 1
with 35 records played and the opening logged 2, arithmetic that only runs when
their number is absent.

Before this fix the numbering fell straight through to our own counter, so the
sequence above labelled the counted six **2..7** while
:mod:`p2pchase.reports.series_assembly` demands exactly 1..6 once each. That is
not a mislabelled throwaway; it is our own shape guard refusing the counted
result at settlement, on the one game that decides the pass threshold, from a
disagreement neither team would have seen coming.

gal-roy1 warned us about the counter and we mitigated by restarting the doors.
This file exists because that mitigation is worthless: the alignment throwaway
runs *between* the restart and the six.
"""

from __future__ import annotations

from p2pchase.runtime.declaration_trace import note_declaration, opening_sub_game


class _Session:
    def __init__(self, sub_game: int = 1) -> None:
        self.sub_game = sub_game
        self.declared_sub_games: list[int] = []
        self.declaration_keys: list[list[str]] = []


def _step0(session: _Session, number: int) -> None:
    """What their driver sends before each sub-game's first turn."""
    note_declaration(session, {"sub_game_number": number, "role": "police"})


#: Their opening ``submit_turn``: no number, which is the whole problem.
OPENING: dict = {"move": "MOVE:N"}


def test_their_declared_number_beats_our_counter():
    session = _Session(sub_game=1)
    _step0(session, 4)

    assert opening_sub_game(OPENING, session, played=True) == 4


def test_a_number_on_the_turn_itself_still_wins():
    """Precedence: the opening turn outranks the step-0 declaration."""
    session = _Session(sub_game=1)
    _step0(session, 4)

    assert opening_sub_game({"sub_game_number": 5}, session, played=True) == 5


def test_our_counter_is_the_last_resort_only():
    """No declaration anywhere: a guess is all that is left, and it increments."""
    session = _Session(sub_game=3)

    assert opening_sub_game(OPENING, session, played=True) == 4
    assert opening_sub_game(OPENING, session, played=False) == 3


def test_tomorrows_agreed_order_numbers_the_six_one_to_six():
    """THE case: alignment throwaway on sub-game 2, then the counted six."""
    session = _Session(sub_game=1)

    _step0(session, 2)
    throwaway = opening_sub_game(OPENING, session, played=False)
    session.sub_game = throwaway
    played = True

    counted = []
    for declared in range(1, 7):
        _step0(session, declared)
        opened = opening_sub_game(OPENING, session, played=played)
        counted.append(opened)
        session.sub_game = opened
        played = True

    assert throwaway == 2
    assert counted == [1, 2, 3, 4, 5, 6]


def test_the_old_counter_rule_would_have_failed_this():
    """Characterisation of the bug, so nobody reintroduces it as a simplification."""
    sub_game, played, counted = 2, True, []
    for _declared in range(1, 7):
        sub_game = 0 or sub_game + (1 if played else 0)
        counted.append(sub_game)

    assert counted == [3, 4, 5, 6, 7, 8]
    assert counted != [1, 2, 3, 4, 5, 6]


def test_a_declared_zero_is_not_treated_as_a_declaration():
    """``0`` is what a missing key parses to; it must not outrank the counter."""
    session = _Session(sub_game=3)
    _step0(session, 0)

    assert opening_sub_game(OPENING, session, played=True) == 4


def test_the_most_recent_declaration_wins_over_an_older_one():
    session = _Session(sub_game=1)
    _step0(session, 2)
    _step0(session, 5)

    assert opening_sub_game(OPENING, session, played=True) == 5
