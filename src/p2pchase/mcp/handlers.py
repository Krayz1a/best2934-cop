"""Tool handlers, deliberately free of any MCP dependency.

Every tool the server exposes is implemented here as a plain function from dict
to dict. The FastMCP binding in :mod:`p2pchase.mcp.server` is a thin adapter
over this class and contains no logic of its own.

The split is what makes the protocol testable. A unit test can drive a complete
COMMIT / ACK / REVEAL exchange between two handler objects in microseconds, with
no sockets, no ports and no transport library -- which means the interesting
failure cases (a reveal with no commitment, a message for the wrong game, a step
out of order) get tested properly instead of being left to a live match.

Every handler answers with a structured refusal rather than raising. An
exception crossing MCP reaches the opponent as an opaque transport failure it
cannot distinguish from a crash, and rule 6 charges both teams for a stalled
sub-game.
"""

from __future__ import annotations

import logging
from typing import Any

from ..runtime.peer_session import PeerSession
from ..services.negotiation_service import NegotiationService
from ..shared.peer_config import PeerConfig
from . import contracts

LOGGER = logging.getLogger(__name__)


class PeerHandlers:
    """The server side of one peer.

    Input:  tool payloads from the opponent.
    Output: structured responses; side effects on the live session.
    Setup:  a :class:`PeerConfig`, plus the session once a sub-game starts.
    """

    def __init__(self, config: PeerConfig, session: PeerSession | None = None) -> None:
        self.config = config
        self.session = session
        self.negotiation = NegotiationService(config)
        self.aborted_reason = ""

    # ---------------------------------------------------------------- guards
    def _require_session(self) -> PeerSession | None:
        return self.session

    def _check_game(self, payload: dict[str, Any]) -> str:
        """Reject a message aimed at a different game or sub-game."""
        session = self.session
        if session is None:
            return "no sub-game is in progress"
        game_id = str(payload.get("game_id", ""))
        if game_id and game_id != session.game_id:
            return f"game_id mismatch: this peer is playing {session.game_id!r}, not {game_id!r}"
        sub_game = payload.get("sub_game_number")
        if sub_game is not None and int(sub_game) != session.sub_game:
            return (f"sub_game mismatch: this peer is on sub-game {session.sub_game}, "
                    f"message is for {int(sub_game)}")
        return ""

    # ----------------------------------------------------------------- tools
    def hello(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Identify ourselves and publish the fingerprints a match depends on."""
        return contracts.ok(handshake=self.negotiation.handshake().as_dict(),
                    tools=list(contracts.ALL_TOOLS))

    def negotiate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Compare the opponent's fingerprints against ours (rule 11)."""
        agreement = self.negotiation.compare(payload.get("handshake", payload))
        if not agreement.agreed:
            return contracts.error("configuration mismatch", **agreement.as_dict())
        return contracts.ok(**agreement.as_dict())

    def declare_step0(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Accept the opponent's signed hardware declaration (rule 24)."""
        session = self._require_session()
        if session is None:
            return contracts.error("no sub-game is in progress")
        session.opponent_records.append(dict(payload))
        return contracts.ok(step=0)

    def commit_step(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Receive a sealed step. The hash alone reveals nothing."""
        problem = self._check_game(payload)
        if problem:
            return contracts.error(problem)
        assert self.session is not None
        step = int(payload.get("step", 0))
        commitment = str(payload.get("commit", ""))
        if len(commitment) != 64:
            return contracts.error(f"commitment must be a 64-character SHA-256 hex digest, "
                           f"got {len(commitment)} characters")
        self.session.on_commit(step, commitment)
        return contracts.ok(step=step, acknowledged=True)

    def acknowledge_step(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Confirm we hold the opponent's commitment for this step."""
        problem = self._check_game(payload)
        if problem:
            return contracts.error(problem)
        assert self.session is not None
        step = int(payload.get("step", 0))
        held = step in self.session.opponent_commitments
        if not held:
            return contracts.error(f"no commitment held for step {step}")
        return contracts.ok(step=step, commit=self.session.opponent_commitments[step])

    def reveal_step(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Receive the disclosed move, hint and barrier for a committed step."""
        problem = self._check_game(payload)
        if problem:
            return contracts.error(problem)
        assert self.session is not None
        step = int(payload.get("step", 0))
        move, hint, barrier = contracts.parse_reveal(payload)
        try:
            self.session.on_reveal(step, move, hint, barrier)
        except ValueError as error:
            return contracts.error(str(error))
        return contracts.ok(step=step, applied=True)

    def sample_scent(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Report our own pheromone intensity at the requested cells."""
        problem = self._check_game(payload)
        if problem:
            return contracts.error(problem)
        assert self.session is not None
        cells = payload.get("cells") or []
        return contracts.ok(samples=self.session.scent_at(cells))

    def final_reveal(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Disclose every nonce so the whole chain becomes checkable (rule 18)."""
        session = self._require_session()
        if session is None:
            return contracts.error("no sub-game is in progress")
        if payload.get("records"):
            session.audit(list(payload["records"]))
        return contracts.ok(records=session.final_reveal(), group=session.group_id)

    def audit_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Verify the opponent's disclosed chain and return the verdict."""
        session = self._require_session()
        if session is None:
            return contracts.error("no sub-game is in progress")
        return contracts.ok(audit=session.audit(list(payload.get("records", []))))

    def agree_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Compare result digests. A mismatch voids the match for both (rule 35)."""
        theirs = str(payload.get("sha256", ""))
        ours = str(payload.get("expected", theirs))
        return contracts.ok(agreed=bool(theirs) and theirs == ours, ours=ours, theirs=theirs)

    def abort(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Accept an abort so neither side is left waiting (rule 6)."""
        self.aborted_reason = str(payload.get("reason", "opponent aborted"))
        LOGGER.error("match aborted by opponent: %s", self.aborted_reason)
        return contracts.ok(aborted=True, reason=self.aborted_reason)

    def as_map(self) -> dict[str, Any]:
        """Tool name -> handler, used by the server binding and by tests."""
        return {
            contracts.TOOL_HELLO: self.hello,
            contracts.TOOL_NEGOTIATE: self.negotiate,
            contracts.TOOL_STEP0: self.declare_step0,
            contracts.TOOL_COMMIT: self.commit_step,
            contracts.TOOL_ACK: self.acknowledge_step,
            contracts.TOOL_REVEAL: self.reveal_step,
            contracts.TOOL_SCENT: self.sample_scent,
            contracts.TOOL_FINAL_REVEAL: self.final_reveal,
            contracts.TOOL_AUDIT: self.audit_result,
            contracts.TOOL_AGREE: self.agree_result,
            contracts.TOOL_ABORT: self.abort,
        }
