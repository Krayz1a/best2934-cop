"""The subject line follows the reader, not the sender's habit.

Two readers with two conventions. The course address is a plus-tagged inbox
(`rmisegal+uoh26finalgame@gmail.com`) that exists to be filtered, so mail sent
there keeps the `[UOH26 Final Game]` bracket. An opponent sorts by the league's
convention, which imreeyal settled from the book on 2026-08-15: no subject is
mandated anywhere -- the only occurrence is the illustrative Appendix A listing
-- so it is convention, and the convention with precedent is the reference form.

The failure this guards against is quiet: one series filed by two teams under
two subject shapes, discovered at a counted settlement rather than before it.
"""

from __future__ import annotations

import pytest

from p2pchase.services.reporting_service import ReportingService

LEAGUE = "rmisegal+uoh26finalgame@gmail.com"


@pytest.fixture
def service(peer_config):
    peer_config.setup.setdefault("email", {})["recipient"] = LEAGUE
    return ReportingService(peer_config)


def _result(winner="best2934"):
    return {
        "game_id": "best2934-vs-imreeyal",
        "final_result": {"winner_group": winner},
    }


def test_course_address_keeps_the_filter_tag(service):
    subject = service.subject(_result(), LEAGUE)
    assert subject.startswith("[UOH26 Final Game]")
    assert "best2934-vs-imreeyal" in subject


def test_no_recipient_given_defaults_to_the_course_form(service):
    """`subject(result)` with no recipient must not silently pick the other form."""
    assert service.subject(_result()).startswith("[UOH26 Final Game]")


def test_an_opponent_gets_the_reference_form(service):
    subject = service.subject(_result(), "imreeyal.copthief@gmail.com")
    assert subject == (
        f"Police-Thief series result: winner best2934 (reported by {service.config.role})")


def test_a_tied_series_degrades_to_winner_tie(service):
    """imreeyal's own mail says `winner tie`; a missing winner must not read as None."""
    assert "winner tie" in service.subject({"final_result": {}}, "imreeyal.copthief@gmail.com")
    assert "winner tie" in service.subject(_result(winner=None),
                                           "imreeyal.copthief@gmail.com")


def test_compose_puts_the_opponent_form_on_a_redirected_friendly(service):
    """The wiring, not just the helper -- compose must pass the real destination."""
    raw, _ = service.compose(_result(), recipient="imreeyal.copthief@gmail.com")
    assert isinstance(raw, dict) and raw.get("raw")


def test_compose_defaults_to_the_league_address_and_its_form(service):
    raw, name = service.compose(_result())
    assert name == "result_best2934-vs-imreeyal.json"
    assert isinstance(raw, dict) and raw.get("raw")
