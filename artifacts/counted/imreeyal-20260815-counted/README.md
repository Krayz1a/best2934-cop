# Counted series — best2934 vs imreeyal, 2026-08-15 (SETTLED, FILED, CLOSED)

Our **first counted game**, complete and reported. Archived into this
subdirectory — which the non-recursive artifact globs cannot see — so that a
later counted series against a different opponent cannot be assembled together
with it.

That is not a hypothetical: `refresh_result` rebuilds a series from every
matching log on disk, and on 2026-08-15 a leftover tree produced a signed result
mixing one counted sub-game with five friendly ones. The evidence is kept; only
its visibility to the glob is removed.

## Result

```
six sub-games, all six survival -- neither cop captured, in either direction
g1 police survival →imreeyal   g2 thief survival →best2934   g3 police survival →imreeyal
g4 thief  survival →best2934   g5 police survival →imreeyal  g6 thief  survival →best2934

total_score      best2934 47  ·  imreeyal 47
sub_games_won    3 · 3          winner_group null      series_tie true
tie_rule         series_add
mutual_agreement dca08155c7858f3fdbf25ff528aac09c37227d4bf9e79bede7f0c38085e3d90d
games_played     { best2934: 1, imreeyal: 6 }   first_meeting true   diversity nobody
```

imreeyal's audit passed on every sub-game — 36/36 verified, nothing forged,
nothing withheld — and ours likewise. Both teams filed independently and then
cross-diffed the two artifacts key by key on league issue #45; imreeyal recorded
the verdict as **SETTLED**, identical on every shared field.

## Reports filed to the lecturer

```
1a005d476b4d5da0   first report   -- superseded
1a005e554612c750   corrected      -- the live one
```

Two reports exist because of a defect we found and disclosed ourselves: the
first carried `games_played_including_this {best2934: 1, imreeyal: 5}`, with the
opponent's column un-incremented, while the field is named *including this*.
imreeyal had predicted the correct value before the series was played. They
ruled that the team whose block was wrong re-files and theirs stands; the
corrected artifact carries a `_supersedes` field naming the message it replaces,
so a grader reading only the attachment can tell which is live and why there are
two.

**No game, score, winner, audit or digest changed between them** —
`mutual_agreement.sha256` is identical in both, because the standings block sits
outside the agreement scope. Which is exactly why the defect was invisible to
every hash and had to be read by a human.

## Rule 52

This pairing is **spent**. There can be no second counted game against imreeyal.
