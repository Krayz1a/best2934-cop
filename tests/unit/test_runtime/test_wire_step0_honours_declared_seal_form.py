"""The step-0 record that crosses the WIRE, not the one stored beside it.

Step 0 is sealed in two places. ``MatchService.step_zero`` builds the copy that
goes into the log artifact; ``peer_host.sealed_step0`` independently builds the
copy handed to ``ReferenceDriver(step_zero=...)``, which is what gets prepended
to every audit chain we disclose. Same declaration, two sealers.

On 2026-08-18 we fixed the artifact one, wrote a negative-controlled test for
it, then verified the fix by re-sealing the stored log -- which passed, because
the stored log is written by the copy we had just fixed. anrbj666 refused
record 0 of all six windows of that very series. The check and the defect were
in different files and the check could not have failed.

So this test drives the path the wire uses: build the runner, let
``select_driver`` construct the real ``ReferenceDriver``, and re-hash the
``step_zero`` it is holding. Verifying the artifact proves nothing about the
wire, and that is the lesson worth keeping more than the fix itself.

The two sealers should be collapsed into one function -- anrbj666 suggested it
and they are right that duplication is the actual defect. Until they are, the
last test here pins that both produce the same construction, so an edit to one
alone fails rather than silently splitting them again.
"""

from __future__ import annotations

from p2pchase.domain import kit_seal
from p2pchase.mcp.handlers import PeerHandlers
from p2pchase.runtime.peer import PeerRunner
from p2pchase.runtime.peer_host import select_driver
from p2pchase.runtime.peer_session import PeerSession
from p2pchase.services.match_service import MatchService

#: The reference surface, which is what makes `select_driver` build the driver
#: whose `step_zero` rides the wire.
REFERENCE = ["negotiate", "receive_turn", "submit_audit", "receive_control"]
GAME = "rival999-vs-test1234"
OPPONENT = "rival999"


def _driver(peer_config, form: str):
    peer_config.setup.setdefault("opponents", {})[OPPONENT] = {"seal_form": form}
    session = PeerSession(config=peer_config, role="police", game_id=GAME)
    runner = PeerRunner(peer_config, session, client=object())
    runner.opponent_tools = list(REFERENCE)
    return select_driver(runner, PeerHandlers(peer_config, session)), session


def _reseal(record, form):
    return kit_seal.seal(record["payload"], record["nonce"], form)


def test_the_wire_record_recomputes_under_the_declared_form(peer_config):
    """The regression anrbj666 refused six times, on the right object."""
    driver, session = _driver(peer_config, kit_seal.PIPE)

    assert session.opponent == OPPONENT, "the pairing must resolve, or form is moot"
    record = driver.step_zero
    assert record, "no step-0 on the driver means nothing opens the audit chain"

    assert record["commit"] == _reseal(record, kit_seal.PIPE), (
        "the step-0 we DISCLOSE does not recompute under the form we DECLARE; "
        "rule 19 voids the whole chain on this single record"
    )
    assert record["commit"] != _reseal(record, kit_seal.MERGED)


def test_a_pairing_declaring_merged_still_seals_merged(peer_config):
    """The fix must honour the declaration, not swap one constant for another."""
    driver, _ = _driver(peer_config, kit_seal.MERGED)

    assert driver.step_zero["commit"] == _reseal(driver.step_zero, kit_seal.MERGED)


def test_both_seal_sites_agree_on_the_construction(peer_config):
    """One declaration must not be sealed two ways by two files.

    They build separate payloads -- different nonces, different timestamps --
    so the commits cannot be compared directly. What must match is which
    construction each one used, and that is what this recovers.
    """
    driver, session = _driver(peer_config, kit_seal.PIPE)
    stored = MatchService(peer_config).step_zero(session.sub_game, "police", OPPONENT)

    def construction(record):
        for form in (kit_seal.PIPE, kit_seal.MERGED):
            if record["commit"] == _reseal(record, form):
                return form
        return "unrecognised"

    assert construction(driver.step_zero) == construction(stored) == kit_seal.PIPE, (
        "the wire copy and the stored copy of step 0 disagree about how they "
        "were sealed -- which is exactly how the 2026-08-18 fix passed its own "
        "test while the wire stayed refused"
    )
