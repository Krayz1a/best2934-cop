"""Gmail delivery with send-only scope (book rules 30, 33, 34).

Three constraints shape this module, and each one is a rule rather than a
preference.

*Send-only.* :data:`SCOPES` grants ``gmail.send`` and nothing else (rule 30).
The agent has no business reading a mailbox, and a compromised token that can
only send is a far smaller problem than one that can read.

*Attachment, never body text.* The result must travel as an attached JSON file;
a plaintext report is rejected and scores zero (rule 34). So the JSON is
attached as ``application/json`` and the body carries only a human summary.

*Credentials from the environment.* Paths come from environment variables and
the files themselves are git-ignored. Nothing in this module ever writes a
secret into a config file or a log line (rule 39).

The interactive consent flow is deliberately NOT run automatically -- see
:func:`authorize`. A human runs it once, in their own browser.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from .. import constants as K

LOGGER = logging.getLogger(__name__)

#: Send-only. Do not widen this list (rule 30).
SCOPES: tuple[str, ...] = ("https://www.googleapis.com/auth/gmail.send",)


class GmailNotConfigured(RuntimeError):
    """Raised when credentials are absent -- a setup problem, not a bug."""


def credentials_path() -> Path:
    return Path(os.environ.get("P2PCHASE_GMAIL_CREDENTIALS", "credentials.json"))


def token_path() -> Path:
    return Path(os.environ.get("P2PCHASE_GMAIL_TOKEN", "token.json"))


def sender_address() -> str:
    return os.environ.get("P2PCHASE_GMAIL_SENDER", "")


def build_message(subject: str, body: str, attachment_name: str,
                  attachment: dict[str, Any], sender: str = "",
                  recipient: str = K.AGENT_REPORT_EMAIL) -> dict[str, str]:
    """Build the raw, base64url-encoded message the Gmail API expects.

    Separated from sending so the exact bytes can be asserted in a unit test
    without touching the network or holding a credential.
    """
    message = EmailMessage()
    message["To"] = recipient
    message["Subject"] = subject
    if sender:
        message["From"] = sender
    message.set_content(body)

    payload = json.dumps(attachment, indent=2, ensure_ascii=False).encode("utf-8")
    message.add_attachment(payload, maintype="application", subtype="json",
                           filename=attachment_name)
    return {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")}


def load_credentials():
    """Load an existing token, refreshing it if it has expired.

    Never starts an interactive flow. A missing or unrefreshable token is a
    configuration failure the human must resolve, not something an autonomous
    agent should paper over mid-match.
    """
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise GmailNotConfigured(
            "Gmail support needs the optional extra: uv sync --extra gmail"
        ) from exc

    path = token_path()
    if not path.exists():
        raise GmailNotConfigured(
            f"no OAuth token at {path}. Run `uv run p2pchase authorize-gmail` once, "
            f"in a browser, to create it. The token file is git-ignored (rule 40)."
        )
    creds = Credentials.from_authorized_user_file(str(path), list(SCOPES))
    if not creds.valid:
        if not (creds.expired and creds.refresh_token):
            raise GmailNotConfigured(f"the OAuth token at {path} is invalid; re-authorize")
        creds.refresh(Request())
        path.write_text(creds.to_json(), encoding="utf-8")
    return creds


def authorize(port: int = 0) -> Path:
    """Run the one-time consent flow and write the token. Human-invoked only.

    This opens a browser and asks a person to grant send-only access. It is
    exposed through the CLI rather than called by the runtime, because granting
    an OAuth scope is a decision a human makes, not an agent.
    """
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise GmailNotConfigured(
            "Gmail support needs the optional extra: uv sync --extra gmail"
        ) from exc

    source = credentials_path()
    if not source.exists():
        raise GmailNotConfigured(
            f"no OAuth client file at {source}. Create one in Google Cloud Console "
            f"(see docs/GMAIL_SETUP.md) and point P2PCHASE_GMAIL_CREDENTIALS at it."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(source), list(SCOPES))
    creds = flow.run_local_server(port=port)
    destination = token_path()
    destination.write_text(creds.to_json(), encoding="utf-8")
    LOGGER.info("OAuth token written to %s (git-ignored)", destination)
    return destination


def send_raw(raw_message: dict[str, str]) -> dict[str, Any]:
    """Hand one prepared message to the Gmail API.

    Always called through the Gatekeeper (guidelines §5.1) -- never directly.
    """
    from googleapiclient.discovery import build  # pragma: no cover - network path

    service = build("gmail", "v1", credentials=load_credentials(), cache_discovery=False)
    return service.users().messages().send(userId="me", body=raw_message).execute()
