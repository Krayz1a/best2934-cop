"""The gal-roy1 tool surface, spoken by our engine (ADR-019).

Our tools and theirs do the same things under different names, and -- the part
that actually stops a match -- with a different calling convention. Theirs take
one ``payload`` object; ours name every field in the signature. FastMCP refuses
a call whose argument names it does not declare, so two teams that agree on
every rule in the book still lose at move one (rule 6). We hit that failure
inside our own repo last week; there is no reason to relearn it against an
opponent.

We adapt rather than ask them to, for three reasons. Their shape matches the
lecturer's reference server (``negotiate(message)``, ``receive_turn(message)``,
``submit_audit(payload)``), so it is what a third team is likeliest to speak
too; they dial out and drive, which makes our side mostly a matter of answering
correctly; and :class:`~p2pchase.mcp.handlers.PeerHandlers` already takes a
single dict per call, so the whole mismatch was ever only in the server binding.

The turn message was the last thing to land, and it was the only part that was
never a renaming problem. ``submit_turn`` is alternating and carries a turn
token; ours is simultaneous commit-reveal. It refused for weeks rather than
guess, because a translator built on a guess would have passed its own tests and
desynchronised a real match. The reconciliation is in
:mod:`p2pchase.runtime.turn_loop`: a *round* means the same thing in both
protocols, so we drive one side of a round at a time.
"""

from __future__ import annotations

import logging
from typing import Any

from .handlers import PeerHandlers

LOGGER = logging.getLogger(__name__)

#: Their names, in the order CONNECT.md lists them, mapped to ours.
TOOL_HELLO = "hello"
TOOL_PROPOSE_CONFIG = "propose_config"
TOOL_DECLARE_STEP0 = "declare_step0"
TOOL_SUBMIT_TURN = "submit_turn"
TOOL_FINAL_AUDIT = "final_audit"
TOOL_AGREE_RESULT = "agree_result"
TOOL_CONFIRM_RESULT = "confirm_result"


class InteropAdapter:
    """Translates one peer's vocabulary into ours, and back.

    Deliberately holds no state of its own. Everything it knows it asks
    ``handlers`` for, so a match driven through this adapter and a match driven
    through our native surface are the same match, logged the same way and
    audited by the same code (rule 36).
    """

    def __init__(self, handlers: PeerHandlers) -> None:
        self.handlers = handlers
        #: The alternating turn loop, once a sub-game is running. Holds the
        #: round counter, so it outlives a single call.
        self._turns: Any = None

    # ------------------------------------------------------------- handshake
    def hello(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Identify ourselves. They read ``group_id`` and ``schema_version``.

        Our native ``hello`` nests those under ``handshake``; theirs expects
        them at the top level. Both are sent, because a field they ignore costs
        nothing and a field they need and cannot find costs the match.
        """
        answer = self.handlers.hello(payload)
        shake = dict(answer.get("handshake", {}))
        return {**answer, "group_id": shake.get("group_id", ""),
                "schema_version": shake.get("schema_version", ""),
                "counted_games_played": self.counted_games_played()}

    def propose_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Judge a proposed config, or compare fingerprints -- whichever arrived.

        ``{"config": {...}}`` is a *proposal*: hash their object under our
        encoding and answer with the digest, which is what proves the two
        canonicalisations agree (see
        :mod:`p2pchase.services.config_proposal`). ``{"handshake": {...}}`` is
        our own older shape, a comparison of fingerprints already computed.

        Reading the first as the second is the bug that cost a preflight: every
        handshake field was absent from their payload, so we reported three
        mismatches against empty strings and refused a peer who had proposed a
        perfectly legal config.
        """
        proposed = payload.get("config")
        if isinstance(proposed, dict):
            from ..services.config_proposal import ConfigProposalService

            return ConfigProposalService(self.handlers.config).answer(proposed)

        verdict = self.handlers.negotiate(payload)
        # Our own digest lives under ``ours`` and is present on a refusal too.
        # Sending it only on success would be exactly backwards: the digest is
        # most useful in the message that says the two configs disagree.
        ours = dict(verdict.get("ours", {}))
        return {**verdict, "accepted": bool(verdict.get("ok")),
                "config_sha256": ours.get("config_sha256", "")}

    def declare_step0(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Accept their signed hardware and commit-hash declaration (rules 24, 53)."""
        return self.handlers.declare_step0(payload)

    # ------------------------------------------------------------------ play
    def submit_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Their turn arrives; ours rides home in ``reply_turn`` (I-7).

        Receiving a ``TurnMessage`` makes it our move, so one call carries a
        whole round. Piggybacking the reply is what lets them drive the entire
        match over outbound connections only -- neither peer needs the other to
        be dialable, which removes the failure mode a rotating tunnel URL would
        otherwise create.
        """
        session = self.handlers.session
        if session is None:
            return {"ack": False, "error": "no sub-game is in progress"}
        try:
            return self.turns(session).receive(payload)
        except ValueError as error:
            # A turn we cannot apply -- most often a commitment we never saw.
            # Answered rather than raised: an exception crosses MCP as an opaque
            # transport failure and rule 6 charges both teams for the stall.
            LOGGER.warning("refusing a turn at step %s: %s", payload.get("step"), error)
            return {"ack": False, "step": payload.get("step"), "error": str(error)}

    def turns(self, session: Any) -> Any:
        """The turn loop bound to this sub-game, created once and kept.

        Kept because it holds the round counter. Rebuilding it per call would
        restart that at zero every turn, and a nil turn would stop being
        distinguishable from the opening one.
        """
        from ..runtime.turn_loop import TurnLoop

        if self._turns is None or self._turns.session is not session:
            self._turns = TurnLoop(session)
        return self._turns

    def confirm_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        """A concession, and only ever that (their INTEROP.md section 3).

        When a capture lands inside a piggybacked reply, the winner learns it
        won from ``claim_response`` -- but the *loser* is the only side that can
        confirm it, and without that the two peers reach ``agree_result``
        reading the sub-game differently, which voids the match for both of us
        (rule 35). They found this in their own rehearsal and asked us to
        implement it.

        We record what they concede and never let it *award* us anything. A
        message saying we lost is believed, because nobody concedes a game they
        won. A message saying we won is recorded and still checked against our
        own board, because that direction is exactly where a lie would pay.
        """
        session = self.handlers.session
        if session is None:
            return {"ack": False, "error": "no sub-game is in progress"}
        outcome = str(payload.get("outcome", "") or "")
        session.on_opponent_finished(outcome)
        cell = payload.get("cell")
        if payload.get("caught"):
            LOGGER.info("opponent concedes capture at %s", cell)
        settled = self.turns(session).concede(
            outcome, list(cell) if isinstance(cell, (list, tuple)) else None)
        return {"ack": True, "recorded": True, "our_outcome": settled or outcome}

    # -------------------------------------------------------------- endgame
    def final_audit(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Their name for our ``final_reveal``: every nonce, both ways (rule 18)."""
        return self.handlers.final_reveal(payload)

    def our_outcome(self) -> str:
        """How *this* peer read the sub-game it just played.

        Our own board's answer, never the opponent's. The turn loop holds it
        because the turn loop is what ended the sub-game -- a capture it
        settled, a survival it counted out to the horizon. A concession they
        sent is recorded separately and deliberately not consulted here: two
        peers that both answer with whatever the other one claimed agree
        perfectly and prove nothing (rule 35).
        """
        session = self.handlers.session
        if session is None:
            return ""
        return str(self.turns(session).finished or "")

    def agree_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Rule 35, in both dialects: a digest pair, or a named outcome.

        This answered every call with two empty strings for as long as gal-roy1
        had been calling it, through two complete sub-games our cop won. It read
        only ``sha256``/``expected``; they send ``{"outcome": ...}``. Neither
        field was present, so it echoed blanks -- and because it echoed the
        *caller's* fields rather than consulting our own board, it had no view
        of its own to fall back on. Our cop captured their thief twice and our
        own agreement tool could not say so.

        So: their outcome is read from the message, ours is computed from the
        turn loop, and the verdict is over the two. A digest pair, when sent,
        is still compared as before. What can never happen again is ``agreed``
        riding on fields nobody populated -- an agreement that names no outcome
        is not an agreement, and filing one is how an honest team files a void.

        Both spellings go out. They read ``ours``/``theirs`` and INTEROP §3
        documents ``our_outcome``/``their_outcome``; publishing both costs two
        keys, and a completed audited sub-game must not become disputed over
        the name of one.
        """
        from ..reports.agreed import AGREED_SUB_GAME_FIELDS, AGREED_TOTALS_FIELDS

        theirs = str(payload.get("outcome", "") or payload.get("their_outcome", "") or "")
        if not theirs and not payload.get("sha256"):
            verdict = {"ok": True, "agreed": False}
        else:
            verdict = self.handlers.agree_result(payload)
        if theirs or not payload.get("sha256"):
            ours = self.our_outcome()
            # They write "CAPTURE", our constants are "capture". Two peers that
            # settled the same sub-game identically must not disagree over a
            # shift key and void the match for both of us (rule 35).
            agreed = bool(ours) and ours.strip().lower() == theirs.strip().lower()
            verdict = {**verdict, "ours": ours, "theirs": theirs,
                       "our_outcome": ours, "their_outcome": theirs,
                       "agreed": agreed}
        return {**verdict, "digest_covers": {
            "sub_game": list(AGREED_SUB_GAME_FIELDS),
            "totals": list(AGREED_TOTALS_FIELDS)}}

    # ----------------------------------------------------------------- misc
    def counted_games_played(self) -> int:
        """How many counted games we have played (rules 37, 38, 52).

        Read from the ledger, which records the *agreement* that a game counts
        (rule 52) rather than the fact that one was played. Counting result
        artifacts instead would have declared two counted games to our first
        real opponent, both against opponents we invented while testing.
        """
        from ..reports.history import counted_games_played

        return counted_games_played()

    def as_map(self) -> dict[str, Any]:
        """Their tool name -> our callable. One dict argument each, as they send."""
        return {
            TOOL_HELLO: self.hello,
            TOOL_PROPOSE_CONFIG: self.propose_config,
            TOOL_DECLARE_STEP0: self.declare_step0,
            TOOL_SUBMIT_TURN: self.submit_turn,
            TOOL_CONFIRM_RESULT: self.confirm_result,
            TOOL_FINAL_AUDIT: self.final_audit,
            TOOL_AGREE_RESULT: self.agree_result,
        }
