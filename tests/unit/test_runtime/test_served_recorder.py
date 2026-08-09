"""Reports for a sub-game the opponent drove (rule 35, book ch9).

The gap these cover was found by playing, not by reading. On 2026-08-09
gal-roy1 drove two complete sub-games against our cop -- config proposed,
turns exchanged, result confirmed, audit disclosed, ``agree_result`` returned
verified and agreed on their side -- and our side wrote no artifact at all,
because only ``play`` writes artifacts and ``play`` never runs when the peer
is the one driving.

That is survivable in a friendly and fatal in a counted game, and it fails in
the worst possible direction: everything in the log says the game went
perfectly, right up to the moment a report is due and there is nothing to send.
"""

from __future__ import annotations

import pytest

from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.mcp.interop import InteropAdapter
from p2pchase.runtime.peer_session import PeerSession
from p2pchase.runtime.served_recorder import ServedRecorder


@pytest.fixture
def recorder(peer_config) -> ServedRecorder:
    return ServedRecorder(peer_config)


@pytest.fixture
def session(peer_config) -> PeerSession:
    return PeerSession(peer_config, "police", "g", sub_game=1)


# --------------------------------------------------------------- the caller
def test_the_opponent_is_learned_from_the_caller_not_a_flag(recorder):
    """A standing door does not get to choose who walks through it. A cop serve
    booted as ``--opponent imreeyal`` recorded three gal-roy1 sub-games under
    imreeyal's name, which is the whole reason this reads the wire instead."""
    recorder.note_caller({"group_id": "gal-roy1"})
    assert recorder.opponent == "gal-roy1"


def test_a_later_message_without_identity_does_not_erase_the_caller(recorder):
    """Their turns carry no ``group_id``. Letting one blank the field would
    file a whole series under ``unknown`` because the last message was a move."""
    recorder.note_caller({"group_id": "gal-roy1"})
    recorder.note_caller({"step": 4})
    recorder.note_caller({"group_id": "   "})
    assert recorder.opponent == "gal-roy1"


@pytest.mark.parametrize("payload", [None, "not-a-dict", 7])
def test_a_payload_that_is_not_a_message_is_ignored(recorder, payload):
    recorder.note_caller(payload)
    assert recorder.opponent == ""


def test_the_game_id_is_built_from_the_two_group_ids(recorder, peer_config):
    recorder.note_caller({"group_id": "gal-roy1"})
    assert recorder.game_id() == f"{peer_config.group_id}-vs-gal-roy1"


def test_an_unidentified_caller_still_produces_a_usable_game_id(recorder):
    """Better a report filed under ``unknown`` than no report at all: the
    records are real either way and the name can be corrected by hand."""
    assert recorder.game_id().endswith("-vs-unknown")


# -------------------------------------------------------------- the writing
def test_a_settled_sub_game_is_written(recorder, session, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    recorder.note_caller({"group_id": "gal-roy1"})
    written = recorder.settle(session, "capture", 12)
    assert written
    assert any("log_" in str(path) for path in written)


def test_the_same_sub_game_is_not_written_twice(recorder, session, tmp_path, monkeypatch):
    """They may call ``agree_result`` more than once for one sub-game, and the
    opener of the next one settles the previous. Rewriting would stamp a fresh
    ``ended_at`` on a game that ended earlier."""
    monkeypatch.chdir(tmp_path)
    recorder.note_caller({"group_id": "gal-roy1"})
    first = recorder.settle(session, "capture", 12)
    assert first and recorder.settle(session, "capture", 12) == []


def test_an_unsettled_sub_game_writes_nothing(recorder, session, tmp_path, monkeypatch):
    """``settle`` is called at the opener of the next sub-game too, and a peer
    that reconnects mid-series has not finished anything worth reporting."""
    monkeypatch.chdir(tmp_path)
    assert recorder.settle(session, "", 0) == []


def test_no_session_writes_nothing(recorder):
    assert recorder.settle(None, "capture", 3) == []


def test_a_disk_failure_costs_the_report_and_not_the_match(recorder, session, monkeypatch):
    """The sub-game already happened and the opponent is mid-series waiting on
    our answer. Raising here would turn a full disk into a lost match."""
    def explode(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(recorder, "_write", explode)
    assert recorder.settle(session, "capture", 3) == []


# ------------------------------------------------- numbering, through the wire
def test_consecutive_sub_games_are_numbered_in_sequence(peer_config):
    """The regression that made this file necessary. A serve booted at sub-game
    3 labelled all three of gal-roy1's sub-games "3" while they numbered them
    1, 2, 3 -- two peers labelling one sub-game differently, which rule 35
    voids at the report diff for BOTH teams."""
    session = PeerSession(peer_config, "police", "g", sub_game=1)
    adapter = InteropAdapter(PeerHandlers(peer_config, session))
    adapter.turns(session).round = 4
    adapter._restart_if_a_new_sub_game({})
    assert adapter.handlers.session.sub_game == 2


def test_their_number_wins_over_our_count_when_they_send_one(peer_config):
    """Ours is a fallback for a peer that numbers nothing. A peer that does
    number its sub-games is the authority on which one it is playing."""
    session = PeerSession(peer_config, "police", "g", sub_game=1)
    adapter = InteropAdapter(PeerHandlers(peer_config, session))
    adapter.turns(session).round = 4
    adapter._restart_if_a_new_sub_game({"sub_game_number": 5})
    assert adapter.handlers.session.sub_game == 5


def test_a_fresh_session_is_not_advanced_by_a_reconnect(peer_config):
    """Nothing has been played, so this is the same sub-game arriving again --
    advancing here would skip a number and desynchronise the series."""
    session = PeerSession(peer_config, "police", "g", sub_game=1)
    adapter = InteropAdapter(PeerHandlers(peer_config, session))
    adapter._restart_if_a_new_sub_game({})
    assert adapter.handlers.session.sub_game == 1


def test_agreeing_a_result_writes_the_report(peer_config, tmp_path, monkeypatch):
    """The end of a series is the case the next-opener hook cannot cover: there
    is no next opener, and the last sub-game is owed to the lecturer too."""
    monkeypatch.chdir(tmp_path)
    session = PeerSession(peer_config, "police", "g", sub_game=1)
    adapter = InteropAdapter(PeerHandlers(peer_config, session))
    adapter.hello({"group_id": "gal-roy1"})
    adapter.turns(session).finished = "capture"
    adapter.agree_result({"outcome": "CAPTURE"})
    assert ("gal-roy1", 1) in adapter.recorder.recorded
