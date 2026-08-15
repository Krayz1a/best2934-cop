# Voided counted attempt 1 — best2934 vs imreeyal, 2026-08-15 13:41 UTC

These two files are the opening sub-game of our first counted series against
imreeyal. **The sub-game itself was clean**: outcome `survival`, 35 steps,
imreeyal's audit passed, 36/36 steps verified, nothing forged or withheld.

They are quarantined because of where they were written, not what they say.

## What went wrong

`NetworkArtifactService.for_opponent()` reads `counted` from the pairing so no
caller can forget it. We wired it into the **opponent-driven** path
(`served_recorder`) on 2026-08-14. Our **own driver** went through
`P2PChaseSDK.record_networked_sub_game`, which built the service with the plain
constructor — where `counted` defaults to `False`.

We drive the imreeyal pairing. So the flag we flipped at 12:33, announced on
league issue #45, and verified twice that morning was read by the one path we
were not using.

The counted sub-game was therefore written as
`artifacts/log_best2934-vs-imreeyal_g01.json` — **the same filename as the
friendly's sub-game 1 from 2026-08-14 22:05, which it overwrote.**
`refresh_result` then assembled this counted sub-game together with friendly
sub-games 2–6 and produced a result reading 75–35 with
`mutual_agreement c2b2c8b5dbde66b1` — *unchanged*, because both openers happened
to be police-survival.

A wrong artifact that looks exactly like the right one is the only kind that
survives a settlement. That coincidence is the reason this is filed at length
rather than quietly deleted.

## Permanent loss, recorded rather than hidden

**The friendly's `log_..._g01.json` and `config_..._g01.json` are gone.**
Artifact JSON is git-ignored, so no copy exists in either repository, and
`artifacts/friendly-1-1556/` is the *first* friendly, not this one.

`result_best2934-vs-imreeyal.json` is deliberately **left as it stands** and has
not been regenerated. Its digest still matches the report imreeyal verified four
ways and the copy in our sent-mail receipt. Re-running `refresh_result` would
now assemble five sub-games and produce a different, honestly-derived, wrong
answer. The filed result is the evidence; the logs behind one of its rows are
not recoverable.

## The fix

`record_networked_sub_game` now builds its service through `for_opponent`, and
`tests/unit/test_sdk/test_driver_writes_counted_where_it_belongs.py` asserts the
driver's *construction* rather than the service's behaviour — the seam where the
flag was dropped. The quarantine tests were never wrong; nothing tested how the
driver built the thing they tested.
