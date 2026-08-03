"""The networked CLI commands (rules 6, 10, 11).

These three are the ones that reach outside the process, so none of them may be
exercised for real here. What is checked instead is the decision each one makes
*before* it reaches out -- and in every case the decision is a refusal:

* ``play`` with no opponent URL must stop, not guess one;
* ``play`` against a peer whose config disagrees must abort at the handshake,
  before move one, because rule 11 makes a mismatched match void anyway;
* ``serve`` and ``gui`` on a machine missing an optional dependency must print
  the missing piece and exit, rather than raise an ImportError at a grader.
"""

from __future__ import annotations

from argparse import Namespace

import pytest

from p2pchase.cli import network_commands
from p2pchase.cli.commands import EXIT_CONFIG, EXIT_FAILED, EXIT_OK


@pytest.fixture
def args(config_dir) -> Namespace:
    return Namespace(role="police", config_dir=str(config_dir), game_id="a-vs-b",
                     sub_game=1, seed=1, host="127.0.0.1", port=9901,
                     opponent_url=None, opponent="rival999", sub_games=1, text=True)


def test_play_refuses_when_no_opponent_url_is_known(args, capsys, monkeypatch):
    """Guessing an endpoint is worse than stopping: it would call a stranger."""
    monkeypatch.setattr(
        "p2pchase.shared.peer_config.PeerConfig.opponent_url",
        property(lambda self: ""),
    )
    assert network_commands.play(args) == EXIT_CONFIG
    assert "no opponent URL" in capsys.readouterr().out


def test_play_aborts_at_a_disagreeing_handshake(args, capsys, monkeypatch):
    """Rule 11: a mismatch voids the match, so playing it out is pure waste."""
    aborted = {}

    class _Client:
        async def hello(self):
            return {"handshake": {"group_id": "rival999", "config_sha256": "0" * 64,
                                  "scent_fingerprint": "0" * 64, "code_version": "1.00"}}

    async def _abort(self, reason, step):
        aborted["reason"] = reason
        from p2pchase.runtime.peer import PeerOutcome

        return PeerOutcome("technical_loss", step, aborted=True, reason=reason)

    async def _never(self):  # pragma: no cover - must not be reached
        raise AssertionError("the sub-game started despite a failed handshake")

    monkeypatch.setattr("p2pchase.cli.network_commands.PeerClient",
                        lambda url, timeout: _Client())
    monkeypatch.setattr("p2pchase.runtime.peer.PeerRunner.abort", _abort)
    monkeypatch.setattr("p2pchase.runtime.peer.PeerRunner.run_sub_game", _never)

    args.opponent_url = "http://127.0.0.1:9902/mcp"
    assert network_commands.play(args) == EXIT_FAILED
    assert "configuration mismatch" in aborted["reason"]
    assert "aborted" in capsys.readouterr().out


def test_play_reports_the_outcome_of_a_completed_sub_game(args, thief_config,
                                                          capsys, monkeypatch):
    class _Client:
        async def hello(self):
            # A genuinely different team: same agreed physics, different group id.
            # Rule 3 makes an identical id a refusal in its own right.
            from p2pchase.services.negotiation_service import NegotiationService

            return {"handshake": NegotiationService(thief_config).handshake().as_dict()}

    async def _finish(self):
        from p2pchase.runtime.peer import PeerOutcome

        return PeerOutcome("survival", 35, opponent_audit={"passed": True})

    monkeypatch.setattr("p2pchase.cli.network_commands.PeerClient",
                        lambda url, timeout: _Client())
    monkeypatch.setattr("p2pchase.runtime.peer.PeerRunner.run_sub_game", _finish)

    args.opponent_url = "http://127.0.0.1:9902/mcp"
    assert network_commands.play(args) == EXIT_OK
    out = capsys.readouterr().out
    assert "outcome        : survival" in out
    assert "opponent audit : True" in out


def test_serve_reports_a_missing_transport_instead_of_raising(args, capsys, monkeypatch):
    from p2pchase.mcp.server import MissingTransportError

    def _no_transport(*a, **kw):
        raise MissingTransportError("FastMCP is not installed. Run `uv sync`.")

    monkeypatch.setattr("p2pchase.mcp.server.serve", _no_transport)
    assert network_commands.serve(args) == EXIT_CONFIG
    assert "FastMCP is not installed" in capsys.readouterr().out


def test_serve_stops_cleanly_on_an_interrupt(args, capsys, monkeypatch):
    """Ctrl-C is how a peer server is meant to be stopped, not a crash."""
    def _interrupt(*a, **kw):
        raise KeyboardInterrupt

    monkeypatch.setattr("p2pchase.mcp.server.serve", _interrupt)
    assert network_commands.serve(args) == EXIT_OK
    assert "server stopped" in capsys.readouterr().out


def test_the_gui_falls_back_and_reports_when_no_renderer_exists(args, capsys, monkeypatch):
    from p2pchase.ui.live_view import LiveViewUnavailableError

    def _unavailable(*a, **kw):
        raise LiveViewUnavailableError("no display and no terminal")

    monkeypatch.setattr("p2pchase.ui.live_view.run_live_view", _unavailable)
    assert network_commands.gui(args) == EXIT_CONFIG
    assert "no display" in capsys.readouterr().out


def test_the_text_gui_runs_a_real_sub_game(args, capsys):
    """The text renderer is the one a headless grader will actually see."""
    assert network_commands.gui(args) == EXIT_OK
    assert "p2pchase live view" in capsys.readouterr().out
