"""The sync tool derives the code; it must not touch what was played.

``tools/sync_thief.py`` mirrors this repository onto the thief's, and it did so
by ``rmtree`` on every directory before writing it. ``artifacts/`` was one of
those directories.

Rule 41 puts our cop and our thief in separate repositories, so a six-sub-game
series leaves three logs in each -- the two directories hold different halves of
one match, not two copies of the same half. Mirroring one onto the other is
therefore not a redundant copy. It is a deletion.

On 2026-08-14 a routine sync deleted the thief's g02, g04 and g06 logs from the
imreeyal friendly: sealed records carrying our own nonces, which is the evidence
an opponent's audit checks us against. They were git-ignored by design, so there
was no version of them to restore from; a stale working copy is the only reason
this is a test and not a loss.

Had it happened after a counted series we would have had no answer to an audit
at all, and rule 35 voids a match whose records cannot be produced.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
import sync_thief  # noqa: E402

#: What must survive a sync, and why each one is on the list.
RECORDS = {
    "artifacts": "log_best2934-vs-imreeyal_g02.json",  # sealed match records
    "logs": "serve.log",                               # what the peer did
    "results": "sweep.json",                           # measured, not derived
}


@pytest.fixture
def target(tmp_path, monkeypatch) -> Path:
    """A thief repository holding its own half of a series, and nothing of ours."""
    source = tmp_path / "cop"
    (source / "src").mkdir(parents=True)
    (source / "src" / "engine.py").write_text("old\n", encoding="utf-8")
    destination = tmp_path / "thief"
    for directory, filename in RECORDS.items():
        (source / directory).mkdir(parents=True)
        (source / directory / "ours.json").write_text("{}", encoding="utf-8")
        (destination / directory).mkdir(parents=True)
        (destination / directory / filename).write_text('{"theirs": true}',
                                                        encoding="utf-8")
    monkeypatch.setattr(sync_thief, "REPO", source)
    return destination


def test_the_other_half_of_the_series_survives_a_sync(target):
    sync_thief._copy(target)

    for directory, filename in RECORDS.items():
        assert (target / directory / filename).exists(), (
            f"{directory}/{filename} was deleted by a code sync")


def test_our_own_records_are_not_pushed_across_either(target):
    """The other direction, and the reason this is ``KEEP`` and not "merge".

    Copying our three logs into their repository would make each side look like
    it played all six, which is a different way to file a report that does not
    match the board.
    """
    sync_thief._copy(target)

    assert not (target / "artifacts" / "ours.json").exists()


def test_the_code_is_still_mirrored(target):
    """The tool has to keep doing its job -- a fix made here must reach there."""
    sync_thief._copy(target)

    assert (target / "src" / "engine.py").read_text(encoding="utf-8") == "old\n"
