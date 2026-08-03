"""Gmail message construction and credential handling (rules 30, 34, 39, 40).

Nothing here touches the network or holds a real credential. What it does check
are the three properties that turn a working mailer into a compliant one:

* the OAuth scope stays send-only (rule 30);
* the report travels as an attached JSON file, not as body text (rule 34) --
  a plaintext report scores zero;
* a missing token raises a clear configuration error instead of silently
  launching a browser consent flow mid-match (rules 39, 40).
"""

from __future__ import annotations

import base64
import email
import json

import pytest

from p2pchase.infra import gmail_sender
from p2pchase.infra.gmail_sender import (
    SCOPES,
    GmailNotConfiguredError,
    build_message,
    credentials_path,
    sender_address,
    token_path,
)

RESULT = {"game_id": "a-vs-b", "final_result": {"winner_group": "a"}, "hebrew": "שלום"}


def _decode(raw: dict[str, str]) -> email.message.Message:
    return email.message_from_bytes(base64.urlsafe_b64decode(raw["raw"]))


def test_the_scope_is_send_only():
    """Widening this is a rule violation, so it is asserted exactly."""
    assert SCOPES == ("https://www.googleapis.com/auth/gmail.send",)


def test_the_report_travels_as_a_json_attachment(tmp_path):
    message = _decode(build_message("subject", "body", "result_a-vs-b.json", RESULT))
    attachments = [p for p in message.walk()
                   if p.get_filename() == "result_a-vs-b.json"]
    assert len(attachments) == 1
    assert attachments[0].get_content_type() == "application/json"


def test_the_attachment_round_trips_unicode_intact():
    """Hebrew group names and messages must survive base64 and MIME."""
    message = _decode(build_message("s", "b", "r.json", RESULT))
    part = next(p for p in message.walk() if p.get_filename() == "r.json")
    assert json.loads(part.get_payload(decode=True).decode("utf-8")) == RESULT


def test_the_body_carries_a_summary_and_never_the_report_itself():
    """Rule 34: the binding content is the attachment, not the prose."""
    message = _decode(build_message("subject", "human summary here", "r.json", RESULT))
    body = next(p for p in message.walk() if p.get_content_type() == "text/plain")
    text = body.get_payload(decode=True).decode("utf-8")
    assert "human summary here" in text
    assert '"final_result"' not in text


def test_the_recipient_defaults_to_the_league_address():
    from p2pchase import constants

    message = _decode(build_message("s", "b", "r.json", RESULT))
    assert message["To"] == constants.AGENT_REPORT_EMAIL


def test_a_sender_is_only_set_when_one_is_configured():
    with_sender = _decode(build_message("s", "b", "r.json", RESULT, sender="me@example.com"))
    without = _decode(build_message("s", "b", "r.json", RESULT))
    assert with_sender["From"] == "me@example.com"
    assert without["From"] is None


def test_credential_locations_come_from_the_environment(monkeypatch, tmp_path):
    """Rule 39: paths are configured, and the files themselves stay out of git."""
    monkeypatch.setenv("P2PCHASE_GMAIL_CREDENTIALS", str(tmp_path / "client.json"))
    monkeypatch.setenv("P2PCHASE_GMAIL_TOKEN", str(tmp_path / "token.json"))
    monkeypatch.setenv("P2PCHASE_GMAIL_SENDER", "agent@example.com")
    assert credentials_path() == tmp_path / "client.json"
    assert token_path() == tmp_path / "token.json"
    assert sender_address() == "agent@example.com"


def test_a_missing_token_is_a_configuration_error_not_a_browser_popup(monkeypatch, tmp_path):
    """An autonomous agent must never open a consent screen mid-match."""
    pytest.importorskip("google.oauth2", reason="Gmail extra not installed")
    monkeypatch.setenv("P2PCHASE_GMAIL_TOKEN", str(tmp_path / "absent.json"))
    with pytest.raises(GmailNotConfiguredError, match="no OAuth token"):
        gmail_sender.load_credentials()


def test_authorizing_without_a_client_file_explains_what_to_create(monkeypatch, tmp_path):
    pytest.importorskip("google_auth_oauthlib", reason="Gmail extra not installed")
    monkeypatch.setenv("P2PCHASE_GMAIL_CREDENTIALS", str(tmp_path / "absent.json"))
    with pytest.raises(GmailNotConfiguredError, match="Google Cloud Console"):
        gmail_sender.authorize()
