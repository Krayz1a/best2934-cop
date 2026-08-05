"""The protocol, driven through the handlers with no transport at all.

This is why the handlers were kept free of any MCP dependency: a complete
COMMIT / ACK / REVEAL exchange runs here in microseconds, so the failure cases
that matter get tested properly instead of being left to a live match.
"""

from __future__ import annotations

import pytest

from p2pchase.mcp import contracts
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.runtime.peer_session import PeerSession

GAME = "test1234-vs-rival999"


@pytest.fixture
def session(peer_config):
    return PeerSession(peer_config, "police", GAME, sub_game=1, seed=1)


@pytest.fixture
def handlers(peer_config, session):
    return PeerHandlers(peer_config, session)


@pytest.fixture
def opponent(thief_config):
    return PeerHandlers(thief_config, PeerSession(thief_config, "thief", GAME, seed=2))


def test_hello_publishes_the_fingerprints_and_the_tool_list(handlers):
    response = handlers.hello()
    assert response["ok"]
    assert response["handshake"]["config_sha256"]
    assert set(response["tools"]) == set(contracts.PUBLISHED_TOOLS)


def test_negotiation_agrees_with_a_matching_opponent(handlers, opponent):
    response = handlers.negotiate({"handshake": opponent.hello()["handshake"]})
    assert response["ok"], response.get("mismatches")


def test_negotiation_refuses_a_different_config(handlers, opponent):
    """Rule 11: byte-identical or no match."""
    theirs = opponent.hello()["handshake"]
    theirs["config_sha256"] = "0" * 64
    response = handlers.negotiate({"handshake": theirs})
    assert not response["ok"]
    assert any("config_sha256" in m for m in response["mismatches"])


def test_negotiation_refuses_a_different_scent_kernel(handlers, opponent):
    """A silent kernel disagreement corrupts the only unforgeable evidence."""
    theirs = opponent.hello()["handshake"]
    theirs["scent_fingerprint"] = "deadbeef"
    response = handlers.negotiate({"handshake": theirs})
    assert any("scent_fingerprint" in m for m in response["mismatches"])


def test_negotiation_catches_a_group_id_collision(handlers):
    response = handlers.negotiate({"handshake": handlers.hello()["handshake"]})
    assert any("collision" in m for m in response["mismatches"])


def test_a_commitment_is_accepted_and_held(handlers):
    response = handlers.commit_step({
        "game_id": GAME, "sub_game_number": 1, "step": 1, "commit": "a" * 64,
    })
    assert response["ok"]
    assert handlers.session.opponent_commitments[1] == "a" * 64


def test_a_malformed_digest_is_refused(handlers):
    response = handlers.commit_step({
        "game_id": GAME, "sub_game_number": 1, "step": 1, "commit": "short",
    })
    assert not response["ok"]
    assert "64-character" in response["reason"]


def test_a_message_for_another_game_is_refused(handlers):
    response = handlers.commit_step({
        "game_id": "someone-else", "sub_game_number": 1, "step": 1, "commit": "a" * 64,
    })
    assert not response["ok"]
    assert "game_id mismatch" in response["reason"]


def test_a_message_for_another_sub_game_is_refused(handlers):
    response = handlers.commit_step({
        "game_id": GAME, "sub_game_number": 4, "step": 1, "commit": "a" * 64,
    })
    assert "sub_game mismatch" in response["reason"]


def test_a_reveal_without_a_prior_commitment_is_refused(handlers):
    """The ordering IS the security model; accepting this would void it."""
    response = handlers.reveal_step({
        "game_id": GAME, "sub_game_number": 1, "step": 1, "move": "N", "hint": "hi",
    })
    assert not response["ok"]
    assert "without a prior commitment" in response["reason"]


def test_a_committed_step_may_then_be_revealed(handlers):
    handlers.commit_step({"game_id": GAME, "sub_game_number": 1, "step": 1,
                          "commit": "a" * 64})
    response = handlers.reveal_step({"game_id": GAME, "sub_game_number": 1, "step": 1,
                                     "move": "N", "hint": "north", "barrier": None})
    assert response["ok"]
    assert handlers.session.state.opponent_steps_seen == 1


def test_a_declared_barrier_becomes_hard_fact(handlers):
    handlers.commit_step({"game_id": GAME, "sub_game_number": 1, "step": 1,
                          "commit": "a" * 64})
    handlers.reveal_step({"game_id": GAME, "sub_game_number": 1, "step": 1,
                          "move": "STAY", "hint": "walled", "barrier": [2, 2]})
    assert (2, 2) in handlers.session.state.board.barriers


def test_acknowledgement_confirms_only_what_we_hold(handlers):
    assert not handlers.acknowledge_step({"game_id": GAME, "step": 5})["ok"]
    handlers.commit_step({"game_id": GAME, "sub_game_number": 1, "step": 5,
                          "commit": "b" * 64})
    assert handlers.acknowledge_step({"game_id": GAME, "step": 5})["ok"]


def test_scent_is_reported_only_for_the_cells_asked_about(handlers):
    response = handlers.sample_scent({"game_id": GAME, "step": 1,
                                      "cells": [[0, 0], [6, 6]]})
    assert set(response["samples"]) == {"0,0", "6,6"}
    # The cop starts here and emits, and the start cell is named in the agreed
    # config -- so the opening field is disclosable and the delay line is seeded
    # with it rather than answering silence until the first move.
    assert response["samples"]["0,0"] > 0


def test_the_sampled_field_is_the_lagged_one_not_the_live_one(handlers):
    """I-6, at the tool an opponent actually calls.

    :meth:`PeerSession.scent_at` reading from the delay line is the fix; this is
    the test that fails if it is ever pointed back at ``my_scent``, which is the
    obvious "simplification" for someone who does not know why it is not one.
    """
    handlers.session.prepare_step(1)
    handlers.session.apply_own_step()  # moves, and emits at the new cell
    state = handlers.session.state
    cells = [[r, c] for r in range(7) for c in range(7)]

    samples = handlers.sample_scent({"game_id": GAME, "step": 1, "cells": cells})["samples"]
    live = {f"{r},{c}": state.my_scent.intensity((r, c)) for r, c in
            ((r, c) for r in range(7) for c in range(7))}
    lagged = state.broadcast.transmitted(state.my_scent.grid)

    assert samples != live, "we answered with the field we are emitting right now"
    assert samples == {f"{r},{c}": lagged.get((r, c), 0.0) for r in range(7) for c in range(7)}


def test_the_final_reveal_discloses_nonces(handlers):
    handlers.session.prepare_step(1)
    handlers.session.apply_own_step()
    records = handlers.final_reveal({})["records"]
    assert records and "nonce" in records[0]


def test_an_audit_verdict_is_returned(handlers):
    handlers.session.prepare_step(1)
    handlers.session.apply_own_step()
    mine = handlers.session.records
    assert handlers.audit_result({"records": mine})["audit"]["passed"]


def test_agreement_compares_digests(handlers):
    assert handlers.agree_result({"sha256": "abc", "expected": "abc"})["agreed"]
    assert not handlers.agree_result({"sha256": "abc", "expected": "xyz"})["agreed"]
    assert not handlers.agree_result({"sha256": ""})["agreed"]


def test_an_abort_is_accepted_so_nobody_is_left_waiting(handlers):
    response = handlers.abort({"reason": "watchdog"})
    assert response["aborted"]
    assert handlers.aborted_reason == "watchdog"


def test_tools_are_refused_cleanly_before_a_sub_game_starts(peer_config):
    idle = PeerHandlers(peer_config)
    assert not idle.commit_step({"step": 1, "commit": "a" * 64})["ok"]
    assert not idle.final_reveal({})["ok"]
    assert not idle.audit_result({"records": []})["ok"]


def test_step0_accepts_the_complementary_role(handlers):
    """The ordinary case: they declare the other side, and we record it.

    ``rival999`` sorts before ``test1234``, so sub-game 4 is the one where the
    agreed rule makes us the cop against them.
    """
    handlers.session.sub_game = 4
    response = handlers.declare_step0({"role": "THIEF", "group_id": "rival999",
                                       "spec": {"os": "linux"}})
    assert response["ok"], response.get("reason")
    assert response["role_checked"] is True
    assert handlers.session.opponent_records


def test_step0_refuses_a_peer_that_also_thinks_it_is_the_cop(handlers):
    """Two cops chase nobody, and rule 6 charges both teams for the stall.

    Caught before move one is the whole point: caught at move one, it is an
    unplayable sub-game neither side can rescue.
    """
    response = handlers.declare_step0({"role": "COP", "group_id": "rival999"})
    assert response["ok"] is False
    assert "role clash" in response["reason"]
    assert not handlers.session.opponent_records, "a refused declaration is not recorded"


def test_step0_refuses_a_complementary_pair_that_has_the_series_backwards(handlers):
    """Playable, complementary, and scored against the wrong halves.

    Our session is the cop at sub-game 1, where the rule makes ``rival999`` the
    cop; a check that only looked for one-of-each would wave this through.
    """
    response = handlers.declare_step0({"role": "THIEF", "group_id": "rival999"})
    assert response["ok"] is False
    assert "sub-game 1" in response["reason"]


def test_step0_records_an_undeclared_role_without_inventing_a_verdict(handlers):
    """A peer that declares no role cannot be checked, and the answer says so."""
    response = handlers.declare_step0({"spec": {"os": "linux"}, "group_id": "rival999"})
    assert response["ok"]
    assert response["role_checked"] is False
    assert handlers.session.opponent_records
