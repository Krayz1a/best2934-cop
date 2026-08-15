"""The mailed body, the attachment and the file on disk must be one object.

imreeyal's settlement check is literally ``body == attachment == thread
artifact``, and rule 35 turns any unexplained difference between two renderings
of one report into a voided sub-game for *both* teams. The danger is not a
wrong number; it is two byte-strings that parse to the same object and do not
match, because then no reader can say which one is the report.

``build_message`` has carried a comment claiming "ONE serialization, used
twice" since it was written. It was not true: ``EmailMessage.set_content``
appends a trailing newline when the text lacks one and ``add_attachment`` does
not, so the body came out one byte longer than the attachment. Nothing caught
it because every existing test compared *parsed* JSON, which is exactly the
comparison that cannot see this class of bug.

So these tests compare bytes, and they compare against a real artifact written
by ``write_json`` rather than a hand-built dict -- the on-disk file is the third
party to the equality and the only one with an independent serializer.
"""

from __future__ import annotations

import base64
import email
import json

from p2pchase.infra import gmail_sender
from p2pchase.reports.naming import write_json


def _parts(raw: dict[str, str]) -> tuple[bytes, bytes]:
    """The decoded body and attachment bytes of a composed message."""
    message = email.message_from_bytes(base64.urlsafe_b64decode(raw["raw"]))
    body = attachment = b""
    for part in message.walk():
        if part.get_filename():
            attachment = part.get_payload(decode=True)
        elif part.get_content_type() == "text/plain":
            body = part.get_payload(decode=True)
    return body, attachment


def _artifact(tmp_path):
    payload = {
        "game_id": "best2934-vs-imreeyal",
        "final_result": {"total_score": {"best2934": 75, "imreeyal": 35}},
        "note": "non-ascii on purpose: ניצחון",
    }
    path = write_json(tmp_path / "result_best2934-vs-imreeyal.json", payload)
    return path, payload


def test_body_and_attachment_are_the_same_bytes(tmp_path):
    _, payload = _artifact(tmp_path)
    body, attachment = _parts(
        gmail_sender.build_message("s", "result.json", payload, recipient="a@b.c"))
    assert body == attachment


def test_body_matches_the_file_on_disk_byte_for_byte(tmp_path):
    path, payload = _artifact(tmp_path)
    body, _ = _parts(
        gmail_sender.build_message("s", "result.json", payload, recipient="a@b.c"))
    assert body == path.read_bytes()


def test_attachment_matches_the_file_on_disk_byte_for_byte(tmp_path):
    path, payload = _artifact(tmp_path)
    _, attachment = _parts(
        gmail_sender.build_message("s", "result.json", payload, recipient="a@b.c"))
    assert attachment == path.read_bytes()


def test_all_three_agree_and_still_parse_to_the_original(tmp_path):
    """Byte equality is the point, but it must not be achieved by corrupting."""
    path, payload = _artifact(tmp_path)
    body, attachment = _parts(
        gmail_sender.build_message("s", "result.json", payload, recipient="a@b.c"))
    assert body == attachment == path.read_bytes()
    assert json.loads(body.decode("utf-8")) == payload


def test_non_ascii_survives_as_utf8_rather_than_escapes(tmp_path):
    """``ensure_ascii=False`` on disk and in the mail, or the bytes diverge.

    Hebrew appears in real reports (the booklet's own field names quote it), and
    a body that escapes it while the file does not is the same failure wearing
    different clothes.
    """
    _, payload = _artifact(tmp_path)
    body, _ = _parts(
        gmail_sender.build_message("s", "result.json", payload, recipient="a@b.c"))
    assert "ניצחון".encode() in body
