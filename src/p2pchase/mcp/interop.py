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

What is *not* settled here is the turn message itself. ``submit_turn`` is
alternating and carries a turn token, where ours is simultaneous commit-reveal,
and the field-by-field schema lives in their ``docs/INTEROP.md``, which we have
asked for and not yet received. Guessing it would produce a translator that
looks finished and is wrong, so :func:`submit_turn` refuses in a legible way
instead -- an answer they can read is worth more than a crash they have to
diagnose.
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

#: Named so the refusal below cannot drift from what we asked them for.
PENDING_SPEC = "docs/INTEROP.md"


class InteropAdapter:
    """Translates one peer's vocabulary into ours, and back.

    Deliberately holds no state of its own. Everything it knows it asks
    ``handlers`` for, so a match driven through this adapter and a match driven
    through our native surface are the same match, logged the same way and
    audited by the same code (rule 36).
    """

    def __init__(self, handlers: PeerHandlers) -> None:
        self.handlers = handlers

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
        """Their name for our ``negotiate``: compare fingerprints (rule 11).

        They expect ``{accepted, config_sha256}``. We answer with both, and
        keep our own richer verdict alongside so a refusal says *why* rather
        than only *no* -- a mismatch found here is free, and the same mismatch
        found at the audit is a void match for both teams.
        """
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
        """Not yet implementable, and saying so plainly is the honest answer.

        Two things are open: their ``TurnMessage`` schema, and whether play is
        alternating with a turn token (which is how we read ``submit_turn``)
        or simultaneous (which is what our engine does today). Neither can be
        inferred safely, and a translator built on a guess would pass its own
        tests and desynchronise a real match.
        """
        step = payload.get("step", "?")
        LOGGER.warning("submit_turn refused at step %s: %s not yet agreed", step, PENDING_SPEC)
        return {"ok": False, "error": "turn schema not yet agreed",
                "need": [f"{PENDING_SPEC} (TurnMessage field list)",
                         "confirm alternating vs simultaneous",
                         "confirm which role moves first in a sub-game"],
                "step": step}

    # -------------------------------------------------------------- endgame
    def final_audit(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Their name for our ``final_reveal``: every nonce, both ways (rule 18)."""
        return self.handlers.final_reveal(payload)

    def agree_result(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Rule 35. A digest computed over different objects can never agree.

        Ours covers only what both peers derive from the same messages, so we
        echo the field list back with the verdict: if their digest disagrees,
        the first question is whether it is over the same object, and that is
        cheaper to answer here than by comparing two filed reports afterwards.
        """
        from ..reports.result import AGREED_FINAL_FIELDS, AGREED_SUB_GAME_FIELDS

        verdict = self.handlers.agree_result(payload)
        return {**verdict, "digest_covers": {
            "sub_game": list(AGREED_SUB_GAME_FIELDS),
            "final_result": list(AGREED_FINAL_FIELDS)}}

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
            TOOL_FINAL_AUDIT: self.final_audit,
            TOOL_AGREE_RESULT: self.agree_result,
        }
