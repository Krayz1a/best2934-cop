"""What crosses the wire when a reference-v3 sub-game ends.

anrbj666 read ``opponent_step_zero: null`` in every window from 2026-08-14 and
were right to call it a rule 53 failure. Our step-0 record was sealed and
written as record 0 of our own log the whole time -- it just never left the
machine, because the driver disclosed the move chain alone.

Their surface publishes ``negotiate``, ``receive_control``, ``receive_turn`` and
``submit_audit``: there is no step-0 tool to call, and ``receive_control`` is
defined by the kit as enable/status/restart/quit and explicitly NOT part of the
sealed record. The chain is the only sealed channel there is.
"""

from __future__ import annotations

import asyncio

from p2pchase.runtime import reference_disclosure


class _Session:
    """The two methods the disclosure touches, and nothing else."""

    opponent = "anrbj666"

    def __init__(self) -> None:
        self.records = [{"step": 1, "payload": {"move": "MOVE:E"}}]

    def final_reveal(self) -> list[dict]:
        return list(self.records)

    def audit(self, records: list[dict]) -> dict:
        return {"verified": len(records)}


STEP_ZERO = {"step": 0, "payload": {"type": "system_spec", "group_id": "best2934"}}


def test_the_sealed_step_zero_is_the_first_record_disclosed():
    """Rule 53 wants it first, not merely present."""
    payload = reference_disclosure.audit_payload(
        _Session(), "thief", "survival", STEP_ZERO)
    assert payload["records"][0] == STEP_ZERO


def test_the_move_chain_still_follows_it_unchanged():
    payload = reference_disclosure.audit_payload(
        _Session(), "thief", "survival", STEP_ZERO)
    assert payload["records"][1:] == _Session().records


def test_without_a_step_zero_we_disclose_the_chain_rather_than_crashing():
    """Losing the declaration is rule 53; losing the audit is rule 36."""
    payload = reference_disclosure.audit_payload(
        _Session(), "thief", "survival", None)
    assert payload["records"] == _Session().records


def test_the_declaration_actually_reaches_their_submit_audit():
    """The bug was never the record. It was that nobody sent it."""
    sent: list[tuple[str, dict]] = []

    class _Client:
        async def call(self, tool: str, payload: dict) -> dict:
            sent.append((tool, payload))
            return {"ok": True}

    class _Inboxes:
        audits: list = []

        def clear(self) -> None:
            pass

    asyncio.run(reference_disclosure.exchange_chains(
        _Client(), _Inboxes(), _Session(), "thief", "survival", STEP_ZERO, 0.01))
    tool, body = sent[0]
    assert tool == "submit_audit"
    assert body["payload"]["records"][0]["payload"]["type"] == "system_spec"
