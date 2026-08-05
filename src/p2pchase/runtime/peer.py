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

from .. import constants
from ..mcp import contracts
from ..shared.peer_config import PeerConfig
from .peer_session import PeerSession
from .watchdog import DeadlineExceededError, TurnDeadline, Watchdog, WatchdogTrippedError

LOGGER = logging.getLogger(__name__)

#: How often to re-check for an inbound message while waiting.
POLL_INTERVAL_SEC = 0.05


class OpponentFinishedError(RuntimeError):
    """The opponent ended the sub-game while we were waiting for their move.

    Carries the outcome they declared. Not a fault: the commonest cause is a
    thief with no legal move left (rule 47), which only the thief can see.
    """


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
        #: True once the opponent has confirmed one of our capture claims.
        self.captured_opponent = False

    # ------------------------------------------------------------- waiting
    async def _await_condition(self, predicate, what: str) -> None:
        """Wait for an inbound message, bounded by both clocks.

        A third way out: the opponent's final reveal may arrive instead of the
        message we asked for, which means the sub-game is over and no further
        message is coming. Waiting out the deadline on a finished game would
        book a technical loss for both of us over an ending we agree about.
        """
        deadline = TurnDeadline(self.turn_timeout)
        while not predicate():
            if self.session.opponent_finished:
                raise OpponentFinishedError(self.session.opponent_finished)
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
        return await self.client.call(contracts.TOOL_COMMIT, contracts.commit_payload(
            self.session.game_id, self.session.sub_game, step,
            self.session.group_id, self.session.role, commitment,
        ))

    async def _push_reveal(self, step: int) -> dict[str, Any]:
        revealed = self.session.reveal()["payload"]
        return await self.client.call(contracts.TOOL_REVEAL, contracts.reveal_payload(
            self.session.game_id, self.session.sub_game, step,
            self.session.group_id, self.session.role,
            move=str(revealed.get("move", "STAY")),
            hint=str(revealed.get("hint", "")),
            barrier=revealed.get("barrier"),
            capture_claim=self.session.capture_claim(),
        ))

    async def _pull_scent(self, step: int) -> None:
        """Ask the opponent for its trail intensity where we think it might be."""
        cells = [list(cell) for cell, _ in self.session.state.belief.top(12)]
        if not cells:
            return
        response = await self.client.call(contracts.TOOL_SCENT, contracts.scent_query(
            self.session.game_id, self.session.sub_game, step, cells))
        if response.get("ok"):
            self.session.absorb_scent(response.get("samples", {}))

    # ----------------------------------------------------------------- loop
    async def play_step(self, step: int) -> None:
        """One full turn, in the order the protocol requires."""
        commitment = self.session.prepare_step(step)
        await self._push_commit(step, commitment)
        await self._await_commit(step)

        response = await self._push_reveal(step)
        # The opponent answers our capture claim in the same round trip. It is
        # their word, sealed against their own record: a false denial is caught
        # at the audit and forfeits the game (rule 22).
        self.captured_opponent = bool(response.get("caught"))
        await self._await_reveal(step)

        self.session.apply_own_step()
        await self._pull_scent(step)
        self.session.end_of_turn()
        self.watchdog.beat()

    async def run_sub_game(self) -> PeerOutcome:
        """Play until capture, survival, the move ceiling, or a fault."""
        max_moves = int(self.config.shared["movement_and_barriers"]["max_moves"])
        outcome = constants.OUTCOME_SURVIVAL
        step = 0

        try:
            for step in range(1, max_moves + 1):
                await self.play_step(step)
                if self._captured():
                    outcome = constants.OUTCOME_CAPTURE
                    break
                if self.session.state.survival_reached():
                    break
        except OpponentFinishedError as ending:
            # They stopped and said why. Their chain arrived with the claim and
            # is audited below, so believing them here costs nothing we cannot
            # check -- and the only ending they can declare unilaterally is one
            # against themselves.
            outcome = str(ending.args[0]) or constants.OUTCOME_SURVIVAL
            LOGGER.info("opponent ended sub-game %d at step %d: %s",
                        self.session.sub_game, step, outcome)
        except (DeadlineExceededError, WatchdogTrippedError) as error:
            if self.session.opponent_finished:
                outcome = self.session.opponent_finished
            else:
                return await self.abort(str(error), step)
        except Exception as error:  # noqa: BLE001 -- any fault must abort cleanly
            # A fault *after* they told us the sub-game was over is expected, not
            # a fault: they have exited, and we were mid-message to a peer that
            # no longer exists. Aborting here would book a technical loss for
            # both of us over an ending we have already agreed on.
            if self.session.opponent_finished:
                LOGGER.info("opponent already ended the sub-game; ignoring %s", error)
                outcome = self.session.opponent_finished
            else:
                LOGGER.exception("unexpected fault during sub-game")
                return await self.abort(f"{type(error).__name__}: {error}", step)

        audit = await self._exchange_chains(outcome)
        LOGGER.info("sub-game %d finished after %d steps: %s (opponent audit: %s)",
                    self.session.sub_game, step, outcome, audit.get("passed"))
        return PeerOutcome(outcome, step, records=self.session.records,
                           opponent_audit=audit)

    async def _exchange_chains(self, outcome: str) -> dict[str, Any]:
        """Disclose our nonces and collect theirs, so both chains can be audited.

        Best-effort by necessity. If they stopped first they have already pushed
        their chain to us and may have exited, so a failure here is expected and
        costs nothing: we audited what they sent when it arrived. Letting the
        exception through would throw away a completed sub-game's artifacts.
        """
        try:
            exchange = await self.client.call(contracts.TOOL_FINAL_REVEAL,
                                              contracts.final_reveal_payload(
                                                  self.session.game_id, self.session.sub_game,
                                                  self.session.group_id,
                                                  self.session.final_reveal(), outcome))
        except Exception:  # noqa: BLE001 -- they may be gone; we still have their chain
            LOGGER.info("could not exchange final reveals; using the chain they already sent",
                        exc_info=True)
            return dict(self.session.last_audit)
        return self.session.audit(list(exchange.get("records", [])))

    def _captured(self) -> bool:
        """Has this sub-game ended in a capture, from either side of the claim?

        Three ways, and a peer sees all three: the thief confirmed our claim, we
        confirmed theirs, or the thief has no legal move left (rule 47). The
        last one is checked locally because only the thief can see it, and it
        would otherwise end the game silently at the move ceiling instead.
        """
        return (self.captured_opponent or self.session.i_am_caught
                or self.session.state.thief_is_boxed_in())

    async def abort(self, reason: str, step: int) -> PeerOutcome:
        """Tell the opponent why we are stopping, then stop.

        The abort is best-effort: if the opponent is already gone, sending fails
        and we swallow it. We are ending the sub-game either way, and a second
        exception here would only hide the first.
        """
        LOGGER.error("aborting sub-game %d at step %d: %s",
                     self.session.sub_game, step, reason)
        try:
            await self.client.call(contracts.TOOL_ABORT, {"reason": reason})
        except Exception:  # noqa: BLE001 - the opponent may already be gone
            LOGGER.debug("could not deliver the abort notice", exc_info=True)
        return PeerOutcome(constants.OUTCOME_TECHNICAL_LOSS, step, aborted=True, reason=reason,
                           records=self.session.records)
