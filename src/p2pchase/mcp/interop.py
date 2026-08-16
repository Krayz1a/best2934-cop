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

from ..runtime import pairing_guard
from ..runtime.declaration_trace import adopt_or_open, note_declaration
from . import contracts
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

    def __init__(self, handlers: PeerHandlers, record_served: bool = False) -> None:
        from ..runtime.served_recorder import ServedRecorder

        self.handlers = handlers
        #: The alternating turn loop, once a sub-game is running. Holds the
        #: round counter, so it outlives a single call.
        self._turns: Any = None
        #: Writes the report artifacts, because nothing else on this path does.
        #: A peer we cannot dial drives the whole match through these tools, and
        #: ``play`` -- which is what normally records a sub-game -- never runs.
        self.recorder = ServedRecorder(handlers.config, record_served)

    # ------------------------------------------------------------- handshake
    def hello(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Identify ourselves. They read ``group_id`` and ``schema_version``.

        Our native ``hello`` nests those under ``handshake``; theirs expects
        them at the top level. Both are sent, because a field they ignore costs
        nothing and a field they need and cannot find costs the match.

        ``role`` rides along because rule 41 puts each role in its own
        repository while both serve the same public URL in turn, and nothing
        else on this endpoint can tell you which one is answering. A listening
        socket behind the agreed URL is not proof it is the right peer: serve
        the cop when the sub-game assigns the thief and every message after the
        handshake is wrong. It is not a disclosure -- both teams derive it from
        the agreed rule and the two group ids before anyone connects.
        """
        self.recorder.note_caller(payload)
        clash = pairing_guard.at_the_door(self, payload)
        if clash:
            return contracts.error(f"wrong pairing: {clash}")
        answer = self.handlers.hello(payload)
        shake = dict(answer.get("handshake", {}))
        session = self.handlers.session
        return {**answer, "group_id": shake.get("group_id", ""),
                "schema_version": shake.get("schema_version", ""),
                "role": session.role if session is not None else "",
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
        self.recorder.note_caller(payload)
        clash = pairing_guard.at_the_door(self, payload)
        if clash:
            return contracts.error(f"wrong pairing: {clash}")
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
        """Accept their signed hardware and commit-hash declaration (rules 24, 53).

        Also the start of a sub-game, which is the part this used to miss. A
        served peer built exactly one :class:`PeerSession` at boot and never
        replaced it, so every sub-game after the first inherited the previous
        one's board *and its round counter*. gal-roy1 drove sub-game 1 four
        times against us and our own log records the result: "declining to act
        at step 0: we are already a move ahead (round 206, opponent has acted
        205 times)". The counter had been climbing across attempts for hours.
        We were not losing those sub-games, we were refusing to play them, and
        the refusal was correct behaviour reading state that should not have
        survived.

        A step-0 declaration means a sub-game is beginning, by definition. So
        if ours has already moved or already ended, this is a new attempt and
        gets a new session -- the same role and game, a clean board.
        """
        self.recorder.note_caller(payload)
        clash = pairing_guard.at_the_door(self, payload)
        if clash:
            return contracts.error(f"wrong pairing: {clash}")
        self._restart_if_a_new_sub_game(payload)
        return self.handlers.declare_step0(payload)

    def _opener_is_a_retry(self, step: int = 0, commit: str = "") -> bool:
        """Whether an opening turn begins a *new* sub-game or repeats this one's.

        A declaration says "a sub-game is beginning" in as many words, so
        :meth:`declare_step0` can restart on our progress alone. A nil turn does
        not: it says "your move", and two of them in a row is the duplicate
        handover gal-roy1 reported against us. Restarting on that one would hand
        them a second of our moves against one of theirs -- a cheat, and a worse
        outcome than the stall it would cure.

        **Step 1 counts as an opener too, and missing that cost us three of
        gal-roy1's four blockers.** We are thief-first: the thief transmits the
        nil handover at step 0 and the cop acts first. So a step-0 message
        arrives only when *they* are the thief -- that is, only when we are the
        cop. Hanging the session reset off it meant ``/cop/mcp`` reset perfectly
        and ``/thief/mcp`` never reset at all, which is exactly what gal-roy1
        measured: 179, 214, 249, 284, 319 records, +35 every sub-game, while our
        cop was clean. By the time we looked it was at 389.

        The two symptoms they filed separately are the same fault. A thief
        carried to step 300+ of a 35-step horizon has nothing left to do, so it
        plays ``MOVE:STAY`` (232 of 249 records), and a thief that has stood
        still for hundreds of turns saturates its own trail into a flat plateau
        with no gradient to read (six cells pinned at 0.81).

        This is the second time we have hung a reset off a message the opponent
        does not always send -- the first was ``declare_step0``, which they have
        never called. The lesson is the same one twice: key the reset on
        evidence a *new sub-game started*, not on one dialect's way of saying so.

        A step-1 turn is held to a stricter test than a step-0 one, because
        step 1 is also the ordinary first move of the sub-game already running
        and a client retrying it must not wipe the board it is playing on.
        Counting rounds is not good enough to tell those apart: the nil handover
        makes our round run one ahead of theirs, so we are already past round 1
        by their first real move.

        The commitment settles it exactly. A retry resends the step it already
        sealed, so the commitment is byte-identical; a new sub-game seals a new
        step, so it cannot be. Holding a *different* commitment for the same
        step is therefore proof of a new sub-game, and needs no counting at all.
        """
        loop = self._turns
        if loop is None:
            return False
        if int(step) > 0:
            held = loop.session.opponent_commitments.get(int(step))
            return bool(loop.finished) or (bool(held) and held != commit)
        return bool(loop.finished) or loop.session.state.opponent_steps_seen > 0

    def _restart_if_a_new_sub_game(self, payload: dict[str, Any]) -> None:
        """Swap in a fresh session when step 0 opens a sub-game we already played.

        Keyed on our own progress rather than on their sub-game number, because
        a peer retrying sub-game 1 sends the same number and still needs a clean
        board. The number is honoured when it is present and different, so a
        series that advances normally is not treated as a retry.

        Called from both openers -- ``declare_step0`` and a step-0
        ``submit_turn`` -- because which one arrives is the opponent's choice of
        dialect, and a peer that opens with a nil turn is starting a sub-game
        just as definitely as one that declares.
        """
        from ..runtime.peer_session import PeerSession

        session = self.handlers.session
        if session is None:
            return
        loop = self._turns
        played = loop is not None and (loop.round > 0 or loop.finished)
        # Record what ARRIVED before deciding anything with it, and BEFORE the
        # opening is computed -- `adopt_or_open` reads the trace this writes.
        note_declaration(session, payload)
        opening, handled = adopt_or_open(payload, session, played, self.recorder)
        if handled:
            return

        # The one we are leaving is finished, and this is the last moment its
        # records exist. A peer that never sends ``agree_result`` -- or whose
        # series is cut short after it -- would otherwise leave no report at all.
        self.recorder.settle(session, str(getattr(loop, "finished", "") or ""),
                             int(getattr(loop, "round", 0) or 0))
        # `opening` came from `adopt_or_open` above: their number on the turn,
        # then the one they declared at step 0, and only then our own counter.
        LOGGER.info("an opening turn starts sub-game %s; clean session (was sub-game %s, "
                    "%d records)", opening, session.sub_game, len(session.records))
        self.handlers.session = PeerSession(session.config, session.role,
            session.game_id, sub_game=opening, seed=session.seed)
        # The fresh session re-derives its opponent from the game id, which is
        # the very assertion the caller outranked. Carry the pairing we learned
        # across, or the next sub-game seals in the default form (ADR-024).
        pairing_guard.adopt(self.handlers.session, {"group_id": session.opponent})
        # And carry the declaration trace, which is ABOUT the payload that
        # opened this new sub-game and so belongs to it, not to the one being
        # retired. `note_declaration` above wrote it onto the outgoing session
        # seconds before this line replaced that session wholesale, so the trace
        # was recorded faithfully and then dropped on the floor every time.
        #
        # That is why, on 2026-08-16, both fields were absent from the log and
        # we could not answer gal-roy1's "what did our driver declare" -- and
        # then quoted our own counter at them as if it were their number. The
        # instrumentation existed and ran; only the last hop was missing.
        note_declaration(self.handlers.session, payload)
        self._turns = None
        self.recorder.opened(opening)

    # ------------------------------------------------------------------ play
    def submit_turn(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Their turn arrives; ours rides home in ``reply_turn`` (I-7).

        Receiving a ``TurnMessage`` makes it our move, so one call carries a
        whole round. Piggybacking the reply is what lets them drive the entire
        match over outbound connections only -- neither peer needs the other to
        be dialable, which removes the failure mode a rotating tunnel URL would
        otherwise create.

        Step 0 restarts the sub-game here too, and not only in
        :meth:`declare_step0`. gal-roy1 opens with a nil turn at step 0 and has
        never once called ``declare_step0`` -- their dialect is
        ``propose_config``, ``submit_turn``, ``confirm_result``. Hanging the
        session reset off a tool the opponent does not call left it inert for
        the only peer it was written for: on 7 August our round counter climbed
        68, 103, 137, 172, 207, 240 across six of their attempts while we
        declined every one, and they recorded a survival at step 35 against a
        cop that never moved.
        """
        step = int(payload.get("step", 0) or 0)
        if step <= 1 and self._opener_is_a_retry(step, str(payload.get("commit") or "")):
            self._restart_if_a_new_sub_game(payload)
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
        return str(self.turns(session).outcome() or "")

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
        # The sub-game is over and both peers have said how it ended, so this is
        # the moment its report exists. Written here rather than at the next
        # opener because a series can stop on its last sub-game, and the last
        # one is no less owed to the lecturer than the first (book ch9).
        self.recorder.settle(self.handlers.session, self.our_outcome(),
                             int(getattr(self._turns, "round", 0) or 0))
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
