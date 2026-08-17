"""Choosing a dialect from what the opponent publishes, not from a flag.

A tool list is the one statement about an opponent that cannot be stale,
wishful or mistranscribed: we asked their running process and it answered.
Everything else -- CONNECT.md, an issue comment, a WhatsApp message -- is a
document about a program rather than the program.

The rule is two-sided on purpose. Reference-v3 is selected only when they
publish ``receive_turn`` *and* do not publish ``commit_step``. Our own protocol
is the one we have played counted games in, so a peer that speaks both is
answered in ours; guessing the newer wire on no evidence would trade a tested
path for an untested one.
"""

from __future__ import annotations

from p2pchase import constants
from p2pchase.mcp import contracts
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.runtime.peer import PeerRunner
from p2pchase.runtime.peer_host import select_driver
from p2pchase.runtime.peer_session import PeerSession
from p2pchase.runtime.reference_driver import ReferenceDriver

#: What imreeyal's server actually published on 2026-08-08 at 19:00.
IMREEYAL = ["negotiate", "receive_turn", "submit_audit", "receive_control"]


def _runner(peer_config, published: list[str]) -> tuple[PeerRunner, PeerHandlers]:
    session = PeerSession(config=peer_config, role=constants.ROLE_COP, game_id="a-vs-b")
    runner = PeerRunner(peer_config, session, client=object())
    runner.opponent_tools = list(published)
    return runner, PeerHandlers(peer_config, session)


def test_the_reference_surface_selects_the_reference_driver(peer_config):
    """The real surface, captured from their live server rather than invented."""
    assert isinstance(select_driver(*_runner(peer_config, IMREEYAL)), ReferenceDriver)


def test_our_own_surface_stays_on_the_long_standing_runner(peer_config):
    assert select_driver(*_runner(peer_config, list(contracts.ALL_TOOLS))) is None


def test_a_peer_speaking_both_is_answered_in_ours(peer_config):
    """Ours is the dialect we have counted games in; theirs is untested here."""
    both = list(contracts.PUBLISHED_TOOLS)
    assert "receive_turn" in both and contracts.TOOL_COMMIT in both
    assert select_driver(*_runner(peer_config, both)) is None


def test_an_unknown_surface_falls_back_rather_than_guessing(peer_config):
    assert select_driver(*_runner(peer_config, ["ping", "status"])) is None


def test_no_surface_at_all_falls_back(peer_config):
    """A peer without ``hello`` still gets a match; an unread list is not evidence."""
    assert select_driver(*_runner(peer_config, [])) is None


def test_the_driver_shares_the_inbox_the_server_actually_fills(peer_config):
    """Two Inboxes objects would mean every wait expiring beside a full queue."""
    runner, handlers = _runner(peer_config, IMREEYAL)
    driver = select_driver(runner, handlers)
    assert driver.inboxes is handlers.reference_inboxes


def test_the_driver_plays_the_same_session_the_handlers_do(peer_config):
    """One board, or the inbound half and the outbound half disagree about it."""
    runner, handlers = _runner(peer_config, IMREEYAL)
    assert select_driver(runner, handlers).session is runner.session


# ------------------------------------------------------------ rule 53 wiring
#
# The record was always sealed and always written as record 0 of our own log.
# What was missing was the hand-off: the driver was built without one, so
# nothing reached anrbj666 and they read `opponent_step_zero: null` for three
# days. These pin the wiring, which is the part that was broken -- a test of
# the disclosure module alone would have passed throughout the outage.

def test_the_reference_driver_is_given_a_sealed_step_zero(peer_config):
    """Their surface has no step-0 tool, so the audit chain is the only way."""
    driver = select_driver(*_runner(peer_config, IMREEYAL))
    assert driver.step_zero is not None


def test_that_step_zero_is_sealed_rather_than_raw(peer_config):
    """Committing it proves we declared it BEFORE the match (rule 24)."""
    driver = select_driver(*_runner(peer_config, IMREEYAL))
    assert driver.step_zero.get("commit"), "an unsealed declaration proves nothing"


def test_it_declares_the_sub_game_it_was_built_for(peer_config):
    driver = select_driver(*_runner(peer_config, IMREEYAL))
    assert driver.step_zero["payload"]["sub_game_number"] == driver.session.sub_game
