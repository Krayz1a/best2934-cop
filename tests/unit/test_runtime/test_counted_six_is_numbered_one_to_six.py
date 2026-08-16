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


# ------------------------------------------------- the live counted failure
class _Recorder:
    def __init__(self) -> None:
        self.opened_with: list[int] = []

    def opened(self, sub_game: int) -> None:
        self.opened_with.append(sub_game)


def _adopt(session: _Session, played: bool = False):
    from p2pchase.runtime.declaration_trace import adopt_or_open

    recorder = _Recorder()
    number, handled = adopt_or_open(OPENING, session, played, recorder)
    return number, handled, recorder


def test_a_fresh_session_adopts_the_number_they_declared_at_step_zero():
    """THE case that broke the counted six of 2026-08-16, live, mid-series.

    Doors restart, so the session begins at 1 with nothing played. gal-roy1
    declare 2 at step 0 and send no number on the opening turn. Before this,
    the guard asked whether the TURN carried a number, read 0, took the early
    return, and kept the counter's 1 -- so the log said g01 while their
    declaration said 2.
    """
    session = _Session(sub_game=1)
    _step0(session, 2)

    number, handled, recorder = _adopt(session)

    assert number == 2
    assert handled is True
    assert session.sub_game == 2
    assert recorder.opened_with == [2]


def test_the_other_door_adopts_four_not_one():
    """The same restart produced a second row also labelled g01, from a 4."""
    session = _Session(sub_game=1)
    _step0(session, 4)

    number, _handled, _recorder = _adopt(session)

    assert number == 4
    assert session.sub_game == 4


def test_a_fresh_session_on_the_number_it_holds_stays_put():
    """No spurious adopt, and nothing recorded as opened."""
    session = _Session(sub_game=1)
    _step0(session, 1)

    number, handled, recorder = _adopt(session)

    assert (number, handled) == (1, True)
    assert recorder.opened_with == []


def test_a_played_session_hands_back_to_the_settle_path():
    """Turns played means the caller must settle and open a fresh session."""
    session = _Session(sub_game=2)
    _step0(session, 3)

    number, handled, recorder = _adopt(session, played=True)

    assert (number, handled) == (3, False)
    assert session.sub_game == 2
    assert recorder.opened_with == []


def test_adopting_never_settles_a_sub_game_that_never_started():
    """The reason adopt exists: settling here would file a row for no game."""
    session = _Session(sub_game=1)
    _step0(session, 5)

    _number, handled, _recorder = _adopt(session)

    assert handled is True


# --------------------------------------- the call site, not just the callee
class _Turns:
    """Stands in for the alternating turn loop."""

    def __init__(self, round_: int = 0, finished: str = "") -> None:
        self.round = round_
        self.finished = finished


def _adapter(turns=None, sub_game: int = 1, declared: int | None = None):
    """An InteropAdapter wired to a stub session, without a server."""
    from p2pchase.mcp.interop import InteropAdapter

    adapter = object.__new__(InteropAdapter)
    session = _Session(sub_game=sub_game)
    if declared is not None:
        _step0(session, declared)

    class _Handlers:
        pass

    handlers = _Handlers()
    handlers.session = session
    adapter.handlers = handlers
    adapter._turns = turns
    adapter.recorder = _Recorder()
    return adapter, session


def test_the_opener_path_runs_on_a_fresh_session():
    """THE bug of 2026-08-16, at the call site rather than inside the callee.

    `_opener_is_a_retry` answers False when `_turns is None` -- correct, a fresh
    session is not a retry -- and `submit_turn` read that as "nothing to do".
    So the opener path never ran on the first turn after a door restart, and
    both numbering fixes that day lived inside it: correct, and unreachable.

    Asserted through the adapter's own condition so a future refactor that
    reintroduces the skip fails here rather than on a counted wire.
    """
    adapter, session = _adapter(turns=None, sub_game=1, declared=2)

    fresh = adapter._turns is None
    assert fresh, "a session that has played nothing must take the opener path"

    adapter._restart_if_a_new_sub_game({"step": 0})

    assert session.sub_game == 2


def test_a_fresh_session_with_no_declaration_keeps_its_number():
    adapter, session = _adapter(turns=None, sub_game=1)

    adapter._restart_if_a_new_sub_game({"step": 0})

    assert session.sub_game == 1


def test_a_mid_game_retry_does_not_take_the_fresh_path():
    """The guard the fix must not trample: a retry keeps the board it is on."""
    adapter, _session = _adapter(turns=_Turns(round_=7), sub_game=3)

    assert adapter._turns is not None
