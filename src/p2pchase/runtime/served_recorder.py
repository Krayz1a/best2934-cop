"""Report artifacts for a sub-game the OPPONENT drove.

``play`` writes artifacts when our own driver finishes a sub-game. That covers
every peer we can dial -- and it does not cover gal-roy1, who cannot be dialled
at all. They publish six tools of their own vocabulary and none of ours, so our
outbound runner's first move comes back ``Unknown tool: 'commit_step'`` and the
match aborts at step 1. Verified on the wire 2026-08-09 12:39. Every sub-game
against them is therefore played through ``serve``, with their client calling
our tools and our side never driving anything.

Until now that path recorded **nothing**. On 2026-08-09 at 12:17 they drove two
complete sub-games against our cop -- ``propose_config``, thirty-five turns,
``confirm_result``, ``final_audit``, ``agree_result``, both verified and agreed
on their side -- and not one artifact file was written.

For a friendly that costs nothing. For a counted game it is fatal, and it is
fatal *silently*: book ch9 has each team send its own report, and a peer-driven
game looks flawless in the log right up to the moment the report is due and
there is nothing on disk to send.

Two things this deliberately does NOT take from the command line:

**The opponent.** ``serve`` is a standing door and the caller decides who walks
through it. A ``--opponent`` flag describes who we *expected*; the ``group_id``
on their messages is who actually arrived. On 2026-08-09 a cop serve started as
``--opponent imreeyal`` recorded three gal-roy1 sub-games under imreeyal's name.

**The sub-game number.** The same run labelled all three of their sub-games "3",
the number it was booted with, while gal-roy1 numbered them 1, 2 and 3. Two
peers labelling one sub-game differently is precisely the disagreement rule 35
voids at the report diff -- and it would have voided it for both teams.
"""

from __future__ import annotations

import logging
from typing import Any

from ..reports.naming import now_iso

LOGGER = logging.getLogger(__name__)


class ServedRecorder:
    """Writes one artifact set per settled sub-game, for a match we did not drive.

    Input:  the caller's payloads, and the session once a sub-game settles.
    Output: ``config_*``, ``log_*``, ``declaration_*`` and ``result_*`` on disk,
            through the same service ``play`` uses -- so a driven match and a
            served one produce the same files, audited by the same code.
    """

    def __init__(self, config: Any, enabled: bool = False) -> None:
        self.config = config
        #: Off unless a standing ``serve`` turned it on. ``play`` writes its own
        #: artifacts when its driver finishes, and a peer that speaks our native
        #: dialect calls ``agree_result`` -- which routes through this adapter --
        #: so leaving it on would have two writers racing for one filename with
        #: two different step counts and two different ``ended_at`` stamps.
        self.enabled = enabled
        #: Who actually called, learned from their messages rather than a flag.
        self.opponent = ""
        self.started: dict[int, str] = {}
        #: Sub-games already on disk. A peer may call ``agree_result`` more than
        #: once for one sub-game, and rewriting the artifacts on the second call
        #: would stamp a fresh ``ended_at`` onto a game that ended earlier.
        self.recorded: set[tuple[str, int]] = set()

    # ------------------------------------------------------------- listening
    def note_caller(self, payload: dict[str, Any] | None) -> None:
        """Remember the caller's ``group_id``. Absent or empty changes nothing.

        Never overwritten with a blank: their turns carry no identity and would
        otherwise erase what their handshake told us.
        """
        if not isinstance(payload, dict):
            return
        group = str(payload.get("group_id") or "").strip()
        if group:
            self.opponent = group

    def opened(self, sub_game: int) -> None:
        """Stamp when a sub-game started, once, so the report spans the real game."""
        self.started.setdefault(int(sub_game), now_iso())

    # ---------------------------------------------------------------- writing
    def game_id(self) -> str:
        """``<us>-vs-<them>``, from the two group ids and nothing else."""
        return f"{self.config.group_id}-vs-{self.opponent or 'unknown'}"

    def settle(self, session: Any, outcome: str, steps: int) -> list[Any]:
        """Write the artifacts for a sub-game that has just ended.

        Silent on an unsettled sub-game: this is called from ``agree_result``
        and from the opener of the *next* sub-game, and only one of those is
        the real ending. Returns the paths written, empty when nothing was.

        A write failure is logged and swallowed. The sub-game already happened
        and its records are in memory; raising here would turn a full disk into
        a lost match, and the opponent is mid-series waiting on our answer.
        """
        if not self.enabled or session is None or not outcome:
            return []
        key = (self.opponent, int(session.sub_game))
        if key in self.recorded:
            return []
        self.recorded.add(key)
        try:
            written = self._write(session, outcome, steps)
        except OSError as error:
            LOGGER.error("could not write artifacts for sub-game %s: %s",
                         session.sub_game, error)
            return []
        LOGGER.info("sub-game %s vs %s settled as %s; %d artifacts written",
                    session.sub_game, self.opponent or "unknown", outcome, len(written))
        return written

    def _write(self, session: Any, outcome: str, steps: int) -> list[Any]:
        from ..runtime.peer import PeerOutcome
        from ..services.network_artifacts import NetworkArtifactService

        result = PeerOutcome(outcome, int(steps), records=list(session.records))
        # Built from the pairing, so a counted series served to us lands in the
        # counted directory without anyone passing a flag. This is the path an
        # *opponent* drives, which is exactly where a forgotten argument would
        # not be noticed until settlement.
        return NetworkArtifactService.for_opponent(
            self.config, self.opponent or "unknown").record_sub_game(
            self.game_id(), int(session.sub_game), session.role,
            self.opponent or "unknown", result,
            self.started.get(int(session.sub_game), now_iso()), now_iso(),
            int(getattr(getattr(session, "talk", None), "tokens_used", 0) or 0))
