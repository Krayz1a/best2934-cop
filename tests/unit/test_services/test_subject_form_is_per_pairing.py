"""One series must file under one subject shape, from both teams.

Our `[UOH26 Final Game]` tag was built to match the course address's
`+uoh26finalgame` plus-tag, which exists to be filtered on, and it stays the
default for that reason. But the shape that matters for a *counted* series is
the one BOTH teams use: two teams filing one match under two subjects is a
settlement the marker has to reconcile by hand.

imreeyal asked for the reference form toward the lecturer before our first
counted series with them -- they have five counted series filed under it. So
the shape became a per-pairing term, like `role_convention` and `scent_model`,
rather than a constant either team has to win an argument about.
"""

from __future__ import annotations

import pytest

from p2pchase.services.reporting_service import ReportingService

REFERENCE = "Police-Thief series result: winner best2934 (reported by police)"


def _result(config, opponent="imreeyal"):
    """A result whose game_id actually names us.

    It has to: `subject` finds the pairing by splitting the game id, so an id
    that does not name our group has no agreement to honour and correctly
    falls back to the tag. Hard-coding "best2934" here made every assertion
    test that fallback instead of the branch it claimed to.
    """
    return {"game_id": f"{config.group_id}-vs-{opponent}",
            "final_result": {"winner_group": "best2934"}}


def _service(peer_config, opponent, form):
    peer_config.setup.setdefault("opponents", {}).setdefault(opponent, {})
    peer_config.setup["opponents"][opponent]["subject_form"] = form
    return ReportingService(peer_config)


def test_an_agreed_reference_pairing_uses_it_for_the_lecturer_too(peer_config):
    """The change imreeyal asked for: our tag must not split their counted series."""
    service = _service(peer_config, "imreeyal", "reference")

    assert service.subject(_result(peer_config), peer_config.email["recipient"]) == REFERENCE


def test_a_pairing_without_the_term_keeps_the_filterable_tag(peer_config):
    service = _service(peer_config, "gal-roy1", "bracket")

    subject = service.subject(_result(peer_config, "gal-roy1"),
                              peer_config.email["recipient"])

    assert subject.startswith("[UOH26 Final Game]")
    assert f"{peer_config.group_id}-vs-gal-roy1" in subject


def test_the_default_is_the_tag_so_an_unconfigured_pairing_still_filters(peer_config):
    """Absent means our tag. A pairing that agreed nothing must stay filterable."""
    peer_config.setup.setdefault("opponents", {})["nobody"] = {}

    assert peer_config.subject_form("nobody") == "bracket"


@pytest.mark.parametrize("form", ["reference", "bracket"])
def test_a_redirected_friendly_always_uses_the_reference_form(peer_config, form):
    """An opponent's inbox sorts by the league convention whatever we agreed."""
    service = _service(peer_config, "imreeyal", form)

    assert service.subject(_result(peer_config), "them@example.com") == REFERENCE


def test_the_subject_the_receipt_reports_is_the_one_the_message_carries(peer_config):
    """The bug this pairing already cost us once, re-asserted for the new branch."""
    service = _service(peer_config, "imreeyal", "reference")
    recipient = peer_config.email["recipient"]

    raw, _ = service.compose(_result(peer_config), recipient)
    import base64
    import email
    message = email.message_from_bytes(base64.urlsafe_b64decode(raw["raw"]))

    assert message["Subject"] == service.subject(_result(peer_config), recipient) == REFERENCE


def test_an_unknown_game_id_falls_back_to_the_tag_rather_than_guessing(peer_config):
    """No opponent in the id means no pairing, so no agreement to honour."""
    service = ReportingService(peer_config)

    subject = service.subject({"game_id": "rehearsal"},
                              peer_config.email["recipient"])

    assert subject.startswith("[UOH26 Final Game]")
