"""The peer orchestrator: driving one sub-game across the network.

Both agents run this identical loop. There is no initiator and no responder --
each peer pushes its own commitment, waits for the other's, then pushes its
reveal and waits for the other's. Symmetry is the point: an asymmetric protocol
would need one side to be trusted with sequencing, and there is nobody to trust.

One step, from this peer's side:

    prepare -> push COMMIT -> await their COMMIT -> push REVEAL
            -> await their REVEAL -> sample their scent -> apply

Waiting is always bounded. Every await carries the agreed response timeout, and
a watchdog measures *progress* across the whole sub-game, so an opponent that
answers promptly while going nowhere still trips it. Rule 6 makes an unfinished
sub-game a technical loss for both teams, which means aborting cleanly is
strictly better than waiting politely.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from .. import constants as K
from ..mcp import contracts as C
from ..shared.peer_config import PeerConfig
from .peer_session import PeerSession
from .watchdog import DeadlineExceeded, TurnDeadline, Watchdog, WatchdogTripped

LOGGER = logging.getLogger(__name__)

#: How often to re-check for an inbound message while waiting.
POLL_INTERVAL_SEC = 0.05


@dataclass
class PeerOutcome:
    """How one networked sub-game ended, from this peer's point of view."""

    outcome: str
    steps: int
    aborted: bool = False
    reason: str = ""
    records: list[dict[str, Any]] = field(default_factory=list)
    opponent_audit: dict[str, Any] = field(default_factory=dict)


class PeerRunner:
    """Plays one sub-game against a live opponent.

    Input:  a :class:`PeerSession` (our private world) and a client that can
            reach the opponent's MCP server.
    Output: a :class:`PeerOutcome` plus a complete, disclosable commit chain.
    Setup:  timeouts come from the agreed config, never from literals.
    """

    def __init__(self, config: PeerConfig, session: PeerSession, client: Any) -> None:
        self.config = config
        self.session = session
        self.client = client
        self.watchdog = Watchdog(timeout_sec=float(config.watchdog_timeout))
        self.turn_timeout = float(config.turn_timeout)

    # ------------------------------------------------------------- waiting
    async def _await_condition(self, predicate, what: str) -> None:
        """Wait for an inbound message, bounded by both clocks."""
        deadline = TurnDeadline(self.turn_timeout)
        while not predicate():
            self.watchdog.check(f"sub-game {self.session.sub_game}")
            deadline.check(what)
            await asyncio.sleep(POLL_INTERVAL_SEC)

    async def _await_commit(self, step: int) -> None:
        await self._await_condition(
            lambda: step in self.session.opponent_commitments,
            f"waiting for the opponent's commitment at step {step}",
        )

    async def _await_reveal(self, step: int) -> None:
        await self._await_condition(
            lambda: self.session.state.opponent_steps_seen >= step,
            f"waiting for the opponent's reveal at step {step}",
        )

    # --------------------------------------------------------------- pushes
    async def _push_commit(self, step: int, commitment: str) -> dict[str, Any]:
        return await self.client.call(C.TOOL_COMMIT, C.commit_payload(
            self.session.game_id, self.session.sub_game, step,
            self.session.group_id, self.session.role, commitment,
        ))

    async def _push_reveal(self, step: int) -> dict[str, Any]:
        revealed = self.session.reveal()["payload"]
        return await self.client.call(C.TOOL_REVEAL, C.reveal_payload(
            self.session.game_id, self.session.sub_game, step,
            self.session.group_id, self.session.role,
            move=str(revealed.get("move", "STAY")),
            hint=str(revealed.get("hint", "")),
            barrier=revealed.get("barrier"),
        ))

    async def _pull_scent(self, step: int) -> None:
        """Ask the opponent for its trail intensity where we think it might be."""
        cells = [list(cell) for cell, _ in self.session.state.belief.top(12)]
        if not cells:
            return
        response = await self.client.call(C.TOOL_SCENT, C.scent_query(
            self.session.game_id, self.session.sub_game, step, cells))
        if response.get("ok"):
            self.session.absorb_scent(response.get("samples", {}))

    # ----------------------------------------------------------------- loop
    async def play_step(self, step: int) -> None:
        """One full turn, in the order the protocol requires."""
        commitment = self.session.prepare_step(step)
        await self._push_commit(step, commitment)
        await self._await_commit(step)

        await self._push_reveal(step)
        await self._await_reveal(step)

        self.session.apply_own_step()
        await self._pull_scent(step)
        self.session.end_of_turn()
        self.watchdog.beat()

    async def run_sub_game(self) -> PeerOutcome:
        """Play until capture, survival, the move ceiling, or a fault."""
        max_moves = int(self.config.shared["movement_and_barriers"]["max_moves"])
        outcome = K.OUTCOME_SURVIVAL
        step = 0

        try:
            for step in range(1, max_moves + 1):
                await self.play_step(step)
                if self.session.state.survival_reached():
                    break
        except (DeadlineExceeded, WatchdogTripped) as error:
            return await self._abort(str(error), step)
        except Exception as error:  # noqa: BLE001 -- any fault must abort cleanly
            LOGGER.exception("unexpected fault during sub-game")
            return await self._abort(f"{type(error).__name__}: {error}", step)

        exchange = await self.client.call(C.TOOL_FINAL_REVEAL,
                                          C.final_reveal_payload(
                                              self.session.game_id, self.session.sub_game,
                                              self.session.group_id,
                                              self.session.final_reveal()))
        audit = self.session.audit(list(exchange.get("records", [])))
        LOGGER.info("sub-game %d finished after %d steps: %s (opponent audit: %s)",
                    self.session.sub_game, step, outcome, audit.get("passed"))
        return PeerOutcome(outcome, step, records=self.session.records,
                           opponent_audit=audit)

    async def _abort(self, reason: str, step: int) -> PeerOutcome:
        """Tell the opponent why we are stopping, then stop.

        The abort is best-effort: if the opponent is already gone, sending fails
        and we swallow it. We are ending the sub-game either way, and a second
        exception here would only hide the first.
        """
        LOGGER.error("aborting sub-game %d at step %d: %s",
                     self.session.sub_game, step, reason)
        try:
            await self.client.call(C.TOOL_ABORT, {"reason": reason})
        except Exception:  # noqa: BLE001 - the opponent may already be gone
            LOGGER.debug("could not deliver the abort notice", exc_info=True)
        return PeerOutcome(K.OUTCOME_TECHNICAL_LOSS, step, aborted=True, reason=reason,
                           records=self.session.records)
