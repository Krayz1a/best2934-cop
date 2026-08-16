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

from ..runtime import declaration_trace
from ..runtime.peer_session import PeerSession
from ..services.negotiation_service import NegotiationService
from ..shared.peer_config import PeerConfig
from . import contracts
from .reference_v3_server import Inboxes

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
        #: Queues behind the reference-v3 tools. They live here rather than in
        #: the server binding so the driver and the handlers reach the *same*
        #: object: a peer that enqueued into one instance while the loop drained
        #: another would wait out every deadline with a full inbox.
        self.reference_inboxes = Inboxes()

    # ---------------------------------------------------------------- guards
    def _require_session(self) -> PeerSession | None:
        return self.session

    def _check_game(self, payload: dict[str, Any]) -> str:
        """Reject a message aimed at a different game or sub-game.

        Also the enforcement point for a refused step 0: see
        :func:`~p2pchase.runtime.declaration_trace.outstanding_clash` for why a
        clash has to be sticky rather than refusing only the call it was raised
        on. A corrected step 0 clears it.
        """
        session = self.session
        if session is None:
            return "no sub-game is in progress"
        clash = declaration_trace.outstanding_clash(session)
        if clash:
            return f"step 0 was refused and nothing has cleared it -- {clash}"
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
        """Identify ourselves and publish the fingerprints a match depends on.

        A caller that names itself gets the locks we agreed with *them*. The
        scent model is a per-pair term -- the book's with anrbj666, the
        reference's with imreeyal -- so a ``hello`` that ignores the caller
        publishes our default to everyone and is simply wrong for one of them.
        ``negotiate`` already re-derives from ``theirs.group_id``; this makes
        the greeting agree with the verdict instead of contradicting it, which
        matters because a readiness gate reads the greeting.

        And when the caller does *not* name itself, the reply says so:
        ``pairing`` is either their group id or the literal ``"default"``.
        imreeyal probed us anonymously on 2026-08-09, read back
        ``multiplicative_book_v1``, and reported it as the wrong model for this
        pairing -- which it is, for them, and it was also the only honest answer
        to a question that had not said who was asking. An unlabelled default is
        indistinguishable from a considered answer, so the label is the fix
        rather than guessing at the caller. ``pairing`` sits beside the
        handshake, never inside it, because everything inside is compared
        against the opponent's copy field by field.
        """
        named = payload if isinstance(payload, dict) else {}
        if not named.get("group_id") and isinstance(named.get("payload"), dict):
            named = named["payload"]
        opponent = str(named.get("group_id", ""))
        return contracts.ok(handshake=self.negotiation.handshake(opponent=opponent).as_dict(),
                            pairing=opponent or "default",
                            tools=list(contracts.PUBLISHED_TOOLS))

    def negotiate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Compare the opponent's fingerprints against ours (rule 11).

        Also *queues* what they sent, which is the half we were missing. On the
        reference-v3 wire ``negotiate`` is a push, not a request: their client
        drops our response body on the floor and blocks until our own agreement
        lands in their inbox. We answered thirteen of imreeyal's calls on
        2026-08-09 and they recorded nought received, correctly -- an answer
        nobody reads is not a reply. The queue is what
        :mod:`p2pchase.runtime.reference_handshake` waits on, and it is filled
        here rather than in a tool because we publish one ``negotiate`` for
        three argument spellings and all three have to feed it.

        Queued before the comparison, and even when the comparison refuses. The
        driver needs to know their agreement *arrived* -- a mismatch is a thing
        to report to them, not a reason to sit waiting for a message we already
        have.
        """
        theirs = payload.get("handshake", payload)
        self.reference_inboxes.queue_agreement(theirs)
        agreement = self.negotiation.compare(theirs)
        if not agreement.agreed:
            return contracts.error("configuration mismatch", **agreement.as_dict())
        return contracts.ok(**agreement.as_dict())

    def declare_step0(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Accept the opponent's signed hardware declaration (rule 24).

        Also the last moment a role clash is cheap. Two peers that both think
        they are the cop chase nobody, and neither discovers it until the moves
        stop making sense -- by which time rule 6 has charged both teams for a
        sub-game that could never have been played. gal-roy1 asked for this
        check and they are right to: the roles are derivable from the sub-game
        number and the two group ids (:mod:`p2pchase.domain.roles`), so a
        disagreement here is a bug in one of the two implementations and is worth
        refusing loudly rather than playing through.

        A peer that declares no role at all is accepted, because we cannot check
        what nobody stated -- but the answer says so plainly rather than reading
        as a clean bill of health.

        The answer names ``responder_role`` and ``caller_role`` rather than
        "ours" and "theirs". Those two words swap meaning depending on which end
        of the wire is reading them, and the first draft of this handler proved
        it: our own log read the answer's "their role" as *their* role, when it
        is the role they read from *us*. A field whose meaning depends on who is
        holding it is a field that will be misread eventually.
        """
        session = self._require_session()
        if session is None:
            return contracts.error("no sub-game is in progress")
        declaration_trace.note_declaration(session, payload)
        number, clash, theirs = declaration_trace.step0_role_check(payload, session, self.config)
        session.role_clash = clash
        if clash:
            LOGGER.error("refusing step 0 for sub-game %s: %s", number, clash)
            return contracts.error(f"role clash: {clash}", responder_role=session.role,
                                   caller_role=theirs, sub_game=number)
        session.opponent_records.append(dict(payload))
        return contracts.ok(step=0, responder_role=session.role, caller_role=theirs,
                            role_checked=bool(theirs), sub_game=number)

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
        claim = contracts.parse_capture_claim(payload)
        try:
            caught = self.session.on_reveal(step, move, hint, barrier, claim)
        except ValueError as error:
            return contracts.error(str(error))
        return contracts.ok(step=step, applied=True, caught=bool(caught))

    def sample_scent(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Report our own pheromone intensity at the requested cells."""
        problem = self._check_game(payload)
        if problem:
            return contracts.error(problem)
        assert self.session is not None
        cells = payload.get("cells") or []
        return contracts.ok(samples=self.session.scent_at(cells))

    def final_reveal(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Disclose every nonce so the whole chain becomes checkable (rule 18).

        Also returns ``commits`` -- step number to the commitment we published
        for that step -- because gal-roy1's auditor could not find one and
        scored every sub-game NOT AUDITED, which under rule 35 makes a counted
        game worthless. The values were always on the wire, one per turn inside
        ``reply_turn.commit``; this only collects them where an auditor looks.

        **An opponent must not trust this map over the one they recorded during
        play.** They are the same numbers only if we are honest, and that is
        precisely the thing an audit exists to test -- gal-roy1 made the point
        themselves: a peer can rewrite a payload, re-seal it, and hand over a
        record set that is perfectly self-consistent. Cross-checking a
        disclosure against a copy from the same disclosure proves nothing. The
        map is a convenience for correlating steps, not evidence; the evidence
        is the commitment they hold from the turn we sent it in.
        """
        session = self._require_session()
        if session is None:
            return contracts.error("no sub-game is in progress")
        if payload.get("records"):
            session.audit(list(payload["records"]))
        # Their final reveal is also the news that they have stopped playing.
        # A peer still waiting for their next commitment has to learn it here or
        # it waits out the deadline for a sub-game that is already over.
        session.on_opponent_finished(str(payload.get("outcome", "")))
        records = session.final_reveal()
        return contracts.ok(records=records, group=session.group_id,
                            commits=_commit_map(records))

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


def _commit_map(records: list[dict[str, Any]]) -> dict[str, str]:
    """Step number to the commitment we published for it.

    Read back out of the disclosed records rather than kept as a second copy,
    so the map cannot drift from the chain it describes. A record with no step
    is skipped rather than keyed under ``"0"``: a wrong correlation is worse
    than a missing one, because the auditor would compare two unrelated steps
    and report a forgery that never happened.
    """
    commits: dict[str, str] = {}
    for record in records:
        step = (record.get("payload") or {}).get("step")
        commit = record.get("commit")
        if step is not None and commit:
            commits[str(int(step))] = str(commit)
    return commits
