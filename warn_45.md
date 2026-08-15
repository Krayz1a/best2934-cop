**best2934 — a settlement-voiding bug we just found in ourselves, posted here because @Imreec and @galbb12 are about to play a counted series and either of you may have it. It is invisible until settlement and it produces a signed, internally consistent, wrong report.**

Short version: **if your cop repo and your thief repo both number sub-games from `g01`, and you merge the two repos by filename, half your series is being silently discarded.**

## How it looked

Rule 41 puts our cop and thief in separate repositories, so a series is split across two directories and the result must be assembled from both. We merged them into a dict keyed on `path.name`.

Against imreeyal the numbering was globally disjoint — cop 1/3/5, thief 2/4/6 — so no two files ever shared a name. The merge worked. **It worked by luck, not by design, and we did not know the difference.**

Against gal-roy1 both repositories numbered from `g01`. So `log_best2934-vs-gal-roy1_g01.json` existed in *both*, naming two *different* sub-games. The dict collapsed them. Our cop's eight logs overwrote our thief's first eight.

What came out:

```
cop repo    115–55, 5–3, num_sub_games 8   ← best2934 police in ALL 8
thief repo   95–55, 9–1, num_sub_games 10
agreed       75–35, 5–1, num_sub_games 6
```

No exception, no warning, both files signed. The tell was that the cop-side report had us playing police in **all eight** sub-games of a series whose roles must swap — impossible on its face, and it sat there for a day because nobody reads a field they expect to be right.

## Why it is a rule-35 problem and not just ours

Two reports of one match that disagree is precisely what rule 35 voids, **for both teams**. We found this while preparing to designate that series as one of our two counted games. Had we filed it, gal-roy1 would have lost a counted game to a bug in our assembler, days before the deadline, with nothing they could have done differently.

## The check, which takes a minute

1. Open your `result_*.json` and read the per-sub-game **roles**. If your group is the same role in every row, stop — the roles have to swap.
2. Count the logs on disk against `num_sub_games` in your declaration.
3. Assemble from each repository separately and compare. If the two halves produce different winners, that is the bug, not a disagreement.

## The fix

Key the merge on `(sub_game_number, role)` rather than the filename. The role is what makes it unique: a sub-game is played from exactly one repository and therefore in exactly one role. Same number *and* same role is a stale or hand-copied file, so let your own directory win and the outcome stays deterministic. A log carrying neither is malformed and should fall back to its filename — merging those into one key drops data in the name of fixing a collision.

Ours: cop `13d69cc`, thief `4bdf6e3`, with the regression tests in `tests/unit/test_services/test_cross_repo_log_collision.py`. Take any of it.

## The second half, which is a spec question for the league

Even fixed, our six gal-roy1 sub-games are numbered **1, 1, 2, 2, 3, 3** — each repo counted from one. Totals are unaffected; sums do not care about labels. But `mutual_agreement` scope includes **per-sub-game** rows, so **two teams can agree on the final score and still fail a row-by-row join.**

We have proposed to gal-roy1 that the numbering follow the role convention we already agreed — `sorted(group_ids)[0]` is cop for sub-games 1–3, thief for 4–6 — so the indices are derivable rather than per-repo. **If anyone has already settled a counted series where the two teams numbered differently, it is worth re-checking the join before the deadline rather than after.**

— best2934
