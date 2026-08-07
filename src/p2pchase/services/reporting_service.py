"""Autonomous result reporting, behind the Gatekeeper (book ch9.3, rules 33-35).

At the end of a match the agent -- not a human -- e-mails the result to the
lecturer. That is what makes it an agent rather than a script someone runs, and
it is also the single most dangerous thing this codebase does: a bug in the
match loop becomes a bug that sends mail in a loop, and Google's answer to that
is to suspend the account.

So every send goes through :class:`~p2pchase.infra.gatekeeper.ApiGatekeeper`.
There is no second path. :meth:`ReportingService.send_result` composes and
delegates; it never calls the API itself.

Rule 35 gives this service its other job: both teams must send, and the two
reports must agree. A dry run is therefore a first-class mode -- the report can
be built, digested and compared with the opponent before anyone sends anything.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..infra import gmail_sender
from ..infra.gatekeeper import ApiGatekeeper, build_gatekeeper
from ..shared.peer_config import PeerConfig

LOGGER = logging.getLogger(__name__)


@dataclass
class DeliveryReceipt:
    """What happened to one report."""

    sent: bool
    recipient: str
    subject: str
    attachment: str
    message_id: str = ""
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "sent": self.sent,
            "recipient": self.recipient,
            "subject": self.subject,
            "attachment": self.attachment,
            "message_id": self.message_id,
            "reason": self.reason,
        }


class ReportingService:
    """Composes the result e-mail and sends it through the Gatekeeper.

    Input:  a result artifact (the dict written to ``result_<game_id>.json``).
    Output: a :class:`DeliveryReceipt`.
    Setup:  a :class:`PeerConfig`; an optional pre-built Gatekeeper, which tests
            inject so no real quota is ever consumed.
    """

    def __init__(self, config: PeerConfig, gatekeeper: ApiGatekeeper | None = None) -> None:
        self.config = config
        self.gatekeeper = gatekeeper or build_gatekeeper(config.rate_limits, "gmail")

    # ------------------------------------------------------------- composing
    def subject(self, result: dict[str, Any]) -> str:
        """Subject line carrying the identifiers a human sorts a mailbox by."""
        return (
            f"[UOH26 Final Game] {result.get('game_id', 'unknown')} — "
            f"{self.config.group_id} result report"
        )

    def body(self, result: dict[str, Any]) -> str:
        """Human-readable summary. The binding content is the attachment."""
        final = result.get("final_result", {})
        lines = [
            f"Group: {self.config.group_id} ({self.config.group_name})",
            f"Members: {', '.join(self.config.members)}",
            f"Game: {result.get('game_id', '')}   uid: {result.get('game_uid', '')}",
            f"Sub-games played: {result.get('num_sub_games', 0)}",
            f"Total score: {final.get('total_score', {})}",
            f"Sub-games won: {final.get('sub_games_won', {})}",
            f"Winner: {final.get('winner_group') or 'series tie'}",
            f"Tokens: {final.get('tokens_total_series', {})}",
            f"Mutual agreement sha256: {result.get('mutual_agreement', {}).get('sha256', '')}",
            "",
            "Cop repository:   " + self.config.repos.get("cop", ""),
            "Thief repository: " + self.config.repos.get("thief", ""),
            "",
            "The binding report is the attached JSON file (rule 34).",
        ]
        return "\n".join(lines)

    def compose(self, result: dict[str, Any]) -> tuple[dict[str, str], str]:
        """Build the raw message and the attachment filename."""
        attachment_name = f"result_{result.get('game_id', 'game')}.json"
        raw = gmail_sender.build_message(
            subject=self.subject(result),
            body=self.body(result),
            attachment_name=attachment_name,
            attachment=result,
            sender=gmail_sender.sender_address(),
            recipient=self.config.email["recipient"],
        )
        return raw, attachment_name

    # ---------------------------------------------------------------- sending
    def incompleteness(self, result: dict[str, Any]) -> str:
        """Why this report must not be sent, or ``""`` when it is complete.

        imreeyal lost a series to exactly this and told us so: their driver
        stopped correctly at sub-game 3, then built and mailed a perfectly
        consistent two-game "series tie" for a six-game match. *Consistent and
        incomplete* is the dangerous shape -- nothing inside the artifact
        contradicts itself, so no self-check inside it can catch the fault, and
        rule 35 charges both teams when the two reports disagree.

        Their advice, adopted verbatim: the completeness check has to be an
        explicit assertion rather than a property of the loop's shape. Ours was
        the latter -- ``run_series`` iterates ``range(1, count + 1)`` and is
        therefore complete by construction, which holds exactly until someone
        adds a ``break`` for a timeout or a lost peer. That is the change most
        likely to be made in a hurry, on the day it matters most.

        Checked against the *signed* ``num_sub_games`` rather than against
        whatever the artifact happens to say, because the artifact's count is
        derived from the same short list that is the bug.
        """
        signed = int(self.config.num_sub_games)
        played = int(result.get("num_sub_games", 0) or 0)
        if played == signed:
            return ""
        return (f"refusing to send an incomplete report: {played} sub-game(s) recorded "
                f"against the signed num_sub_games of {signed}")

    def send_result(self, result: dict[str, Any], dry_run: bool = False) -> DeliveryReceipt:
        """Send one result report. ``dry_run`` composes without delivering."""
        raw, attachment_name = self.compose(result)
        recipient = self.config.email["recipient"]
        subject = self.subject(result)

        short = self.incompleteness(result)
        if short and not dry_run:
            LOGGER.error("%s", short)
            return DeliveryReceipt(False, recipient, subject, attachment_name, reason=short)

        if dry_run or not self.config.email.get("enabled", False):
            reason = "dry run" if dry_run else "email.enabled is false in setup.json"
            LOGGER.info("report composed but NOT sent (%s): %s", reason, subject)
            return DeliveryReceipt(False, recipient, subject, attachment_name, reason=reason)

        try:
            response = self.gatekeeper.execute(
                gmail_sender.send_raw, raw, gate_label="gmail.send"
            )
        except Exception as error:  # noqa: BLE001 -- reported, never swallowed silently
            LOGGER.error("report delivery failed: %s: %s", type(error).__name__, error)
            return DeliveryReceipt(False, recipient, subject, attachment_name,
                                   reason=f"{type(error).__name__}: {error}")

        message_id = str(response.get("id", "")) if isinstance(response, dict) else ""
        LOGGER.info("report delivered to %s (id=%s)", recipient, message_id)
        return DeliveryReceipt(True, recipient, subject, attachment_name, message_id)

    def send_result_file(self, path: Path | str, dry_run: bool = False) -> DeliveryReceipt:
        """Load a written result artifact and send it."""
        import json

        with Path(path).open("r", encoding="utf-8") as handle:
            return self.send_result(json.load(handle), dry_run=dry_run)
