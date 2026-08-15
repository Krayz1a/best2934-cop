"""What we send is what we must check, not what we composed.

We fixed a missing Content-Transfer-Encoding in `build_message`, added three
tests that assert the composed message carries it, watched them pass, and
re-flew the report. imreeyal read the raw `.eml`: the second flight's body was
byte-identical to the first's, still unarmored, still soft-wrapped at the same
ten points.

Every check we owned was on the composer, and the composer was right. So these
tests sit on `send_raw` -- the last function before the API, which cannot be
bypassed because there is no second path to Gmail -- and on the bytes it is
handed rather than on the object a builder returned.
"""

from __future__ import annotations

import base64
import email
import json

import pytest

from p2pchase.infra import gmail_sender


def _raw(**overrides):
    payload = {"game_id": "best2934-vs-imreeyal", "_remark": "prose " * 200}
    return gmail_sender.build_message("s", "result.json", payload,
                                      recipient="a@b.c", **overrides)


def _strip_encoding(raw: dict[str, str]) -> dict[str, str]:
    """The exact defect, reproduced: a wire whose body declares no encoding."""
    wire = base64.urlsafe_b64decode(raw["raw"]).decode("utf-8")
    wire = wire.replace("Content-Transfer-Encoding: base64\n", "", 1)
    return {"raw": base64.urlsafe_b64encode(wire.encode("utf-8")).decode("ascii")}


def test_a_healthy_message_reports_no_armor_problems():
    assert gmail_sender.armor_problems(_raw()) == []


def test_an_unarmored_body_is_detected_from_the_wire_bytes():
    assert gmail_sender.armor_problems(_strip_encoding(_raw())) == ["text/plain"]


def test_send_raw_refuses_an_unarmored_message(monkeypatch):
    """The guard must fire before the API call, not after it."""
    called = []
    monkeypatch.setattr(gmail_sender, "load_credentials", lambda: called.append("creds"))

    with pytest.raises(gmail_sender.UnarmoredMessageError):
        gmail_sender.send_raw(_strip_encoding(_raw()))

    assert called == [], "credentials were loaded before the message was checked"


def test_the_refusal_names_the_offending_part():
    with pytest.raises(gmail_sender.UnarmoredMessageError, match="text/plain"):
        gmail_sender.send_raw(_strip_encoding(_raw()))


def test_the_multipart_container_is_not_itself_expected_to_be_encoded():
    """A `multipart/mixed` wrapper carries no payload, so it needs no encoding."""
    message = email.message_from_bytes(base64.urlsafe_b64decode(_raw()["raw"]))
    assert message.get_content_type() == "multipart/mixed"
    assert message.get("Content-Transfer-Encoding") is None
    assert gmail_sender.armor_problems(_raw()) == []


def test_the_archived_wire_is_the_bytes_handed_to_send(peer_config, tmp_path,
                                                       monkeypatch):
    """The receipt must be the message itself, not a re-rendering of it."""
    from p2pchase.services.reporting_service import ReportingService

    monkeypatch.setattr("p2pchase.services.reporting_service.artifacts_dir",
                        lambda counted=False: tmp_path)
    service = ReportingService(peer_config)
    result = {"game_id": "best2934-vs-imreeyal", "num_sub_games": 6}
    raw = service.compose(result, "a@b.c")[0]

    path = service.archive_wire(raw, result)

    assert path is not None
    assert path.read_bytes() == base64.urlsafe_b64decode(raw["raw"])
    assert path.suffix == ".eml"


def test_an_archived_wire_still_parses_and_carries_its_encoding(peer_config, tmp_path,
                                                               monkeypatch):
    from p2pchase.services.reporting_service import ReportingService

    monkeypatch.setattr("p2pchase.services.reporting_service.artifacts_dir",
                        lambda counted=False: tmp_path)
    service = ReportingService(peer_config)
    result = {"game_id": "best2934-vs-imreeyal", "num_sub_games": 6}
    raw = service.compose(result, "a@b.c")[0]

    message = email.message_from_bytes(service.archive_wire(raw, result).read_bytes())

    parts = {p.get_content_type(): p.get("Content-Transfer-Encoding")
             for p in message.walk() if not p.get_content_type().startswith("multipart/")}
    assert parts == {"text/plain": "base64", "application/json": "base64"}


def test_archiving_never_blocks_a_send(peer_config, tmp_path, monkeypatch):
    """Bookkeeping that can stop a report is worse than no bookkeeping."""
    from p2pchase.services.reporting_service import ReportingService

    monkeypatch.setattr("p2pchase.services.reporting_service.artifacts_dir",
                        lambda counted=False: tmp_path / "does" / "not" / "exist")
    service = ReportingService(peer_config)

    assert service.archive_wire({"raw": "!!!not base64!!!"}, {"game_id": "g"}) is None


def test_the_body_that_would_fly_still_equals_its_attachment():
    """The invariant the whole exercise is about, asserted on decoded wire bytes."""
    message = email.message_from_bytes(base64.urlsafe_b64decode(_raw()["raw"]))
    body = attachment = None
    for part in message.walk():
        if part.get_filename():
            attachment = part.get_payload(decode=True)
        elif part.get_content_type() == "text/plain":
            body = part.get_payload(decode=True)
    assert body == attachment
    assert json.loads(body.decode("utf-8"))["game_id"] == "best2934-vs-imreeyal"
