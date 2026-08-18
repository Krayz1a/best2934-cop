"""Step 0 must be sealed under the form the pairing DECLARES.

Our negotiate publishes `commit_form` from ``config.seal_form(opponent)`` and
our setup block declares ``kit_pipe_v1`` for anrbj666. The turn path honoured
it -- ``peer_session`` and ``session_terminal`` both pass ``form=`` -- and
``MatchService.step_zero`` did not. ``commit`` with no form falls to
``kit_seal.DEFAULT_FORM``, which is ``merged_nonce_v1``, so step 0 was sealed
under one construction while every other record in the same chain used the
other.

That is fatal rather than cosmetic. Rule 19 makes any commit mismatch void the
chain with no interpretation, and the rule-53 fix prepends step 0 to *every*
audit chain we disclose -- so one unrecomputable record voided all six windows
on 2026-08-18 even though the scent frames those same windows carried passed
clean on the opponent's side.

anrbj666 named the call site on 2026-08-18. It was verified here against our
own tree before anything was changed: their claim, our confirmation.

Sealing is only half of an agreement. The other half is that both peers name
the same construction, which is what ``kit_seal.FORMULAE`` publishes and what
this test pins for the record that opens the chain.
"""

from __future__ import annotations

from p2pchase.domain import kit_seal
from p2pchase.services.match_service import MatchService


def _step_zero(config, opponent: str = ""):
    return MatchService(config).step_zero(1, "police", opponent)


def _reseal(record, form: str) -> str:
    return kit_seal.seal(record["payload"], record["nonce"], form)


def test_step_zero_recomputes_under_the_declared_form(peer_config):
    """The regression: pipe declared, pipe sealed."""
    peer_config.setup.setdefault("opponents", {})["rival999"] = {
        "seal_form": kit_seal.PIPE,
    }
    record = _step_zero(peer_config, "rival999")

    assert peer_config.seal_form("rival999") == kit_seal.PIPE
    assert record["commit"] == _reseal(record, kit_seal.PIPE), (
        "step 0 does not recompute under the form this pairing declares; "
        "rule 19 voids the whole chain on a single mismatch"
    )
    assert record["commit"] != _reseal(record, kit_seal.MERGED), (
        "sealed under the kit default while declaring the pipe form -- this is "
        "the exact defect anrbj666 found on 2026-08-18"
    )


def test_a_pairing_that_declares_merged_still_gets_merged(peer_config):
    """The fix must not simply swap one hard-coded form for another."""
    peer_config.setup.setdefault("opponents", {})["rival999"] = {
        "seal_form": kit_seal.MERGED,
    }
    record = _step_zero(peer_config, "rival999")

    assert record["commit"] == _reseal(record, kit_seal.MERGED)


def test_no_opponent_falls_back_to_the_kit_default(peer_config):
    """The local-match path names no pairing, and must keep working.

    ``pairing("")`` is ``{}``, so ``seal_form`` returns the kit default. This
    is the behaviour every caller had before the fix, pinned so that adding the
    argument did not quietly change what a local series seals.
    """
    record = _step_zero(peer_config)

    assert record["commit"] == _reseal(record, kit_seal.DEFAULT_FORM)
