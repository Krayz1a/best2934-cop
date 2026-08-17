# Submission answer sheet

**Template** `uoh-rl07-final-project-2026.docx` · **Deadline** 2026-08-12 23:59
(no extensions) · **Last updated** 2026-08-15

This is the working copy of the Word form. Every field the codebase can answer is
answered here; everything else is marked **[OPERATOR]** with what it needs. Fill
the `.docx`, export to PDF, and submit it **individually in Moodle — one
submission per member**, not one for the group.

---

## 1. Header block

| Template field | Answer |
|---|---|
| Group ID code (8 characters, English, no spaces) | `best2934` |
| Recommendation for self-scoring for the group | **85** — see §4. The games table supports 90 (two counted games, two different groups: imreeyal 2026-08-15 47–47 tie, `gal-roy1` 2026-08-16 lost 30–90) and the operator chose to claim 85 on 2026-08-18. Marking ourselves down needs no justification; `fill_submission.py` still refuses to print more than the table supports |
| Cop repository url | `https://github.com/Krayz1a/best2934-cop` |
| Thief repository url | `https://github.com/Krayz1a/best2934-thief` |
| AI Agent email address that sent the results to the lecturer | `eyalkol2@gmail.com` — **authorised and verified by a live send** on 2026-08-07, see [GMAIL_SETUP.md](GMAIL_SETUP.md) §0. Results go **to** `rmisegal+uoh26finalgame@gmail.com`; this field is the address they arrive **from** |

## 2. Members

The template prints two student blocks. The team has three, so **add a "Student
3" block** with the same five fields before filling it in.

| # | First / Last (English) | Hebrew | ID card |
|---|---|---|---|
| 1 | Tomer Levy | *(in the fill-in sheet)* | *(in the fill-in sheet)* |
| 2 | Eyal Koloshi | *(in the fill-in sheet)* | *(in the fill-in sheet)* |
| 3 | Alon Issman | *(in the fill-in sheet)* | *(in the fill-in sheet)* |

The six values have been transcribed out of `best2934-ex01.pdf` into
`~/uni-project/SUBMISSION_FILL_IN.md`, which is **outside both repositories**
and is to be deleted once the `.docx` is filled in. They are still not written
here, for the reason below.

**The form itself is already generated**: `~/uni-project/fill_submission.py`
writes `best2934-final-project-2026.docx` from one data block — Student 3 block
cloned in, Hebrew names tagged `w:rtl`. It is re-runnable on purpose, because
§3 below changes until the deadline and the script *derives* the self-score
from the length of its games list rather than taking it as a separate value.
A form cannot then claim a grade its own table contradicts. Both the script and
its output stay outside the repositories: they hold ID numbers.

ID numbers and Hebrew spellings are personal data and stay out of this file on
purpose. **This repository is public**, so anything written here is published to
everyone, permanently and irrevocably — a git history cannot be un-pushed. Three
national ID numbers in a public repository would be a disclosure the form never
asked for, and two of the three belong to people who are not the person filling
it in.

They do not need to be retyped from memory. **Every value is already filled in
on `best2934-ex01.pdf`** — same group, same three members, questions 4, 5 and
"Student 3": English names, Hebrew names and ID cards. That file sits beside the
repositories and is not tracked by either.

**Three members is permitted, and the form should say why.** The same PDF
records the reserve-duty exception (Guidelines §8): one member is in active
military reserve service, which is what allows the group to have three members
*and* to submit up to the final-project deadline. If the template has anywhere
to note it, note it — a grader who does not know the exception may read the
third student block, or the timing, as an irregularity rather than a permission.

## 3. Games played

| Template field | Answer today |
|---|---|
| Legal number of games your agent emailed the instructor about | **1** |
| Maximum number of points accumulated | **47** (in the counted series) |
| Games won / lost / drawn | 0 / 0 / **1** |
| Bonus eligibility | Diversity reward not earned — it is paid for a *victory* over a new opponent, and the series was a tie |
| Opponents with a working protocol | **3** (`imreeyal` — counted, tied; `gal-roy1` — counted, lost; `anrbj666` — friendlies only, uncounted) |
| Counted games played | **1** of the 2 needed to pass — read from the ledger, not from the artifacts (rule 52) |

### The counted series: best2934 vs imreeyal, 2026-08-15

```
six sub-games, all six survival -- neither cop captured, in either direction
total_score      best2934 47  ·  imreeyal 47
sub_games_won    3 · 3        winner_group null      series_tie true
mutual_agreement dca08155c7858f3fdbf25ff528aac09c37227d4bf9e79bede7f0c38085e3d90d
filed            Gmail 1a005e554612c750, superseding 1a005d476b4d5da0
```

Both teams filed to the lecturer independently and then cross-diffed the two
artifacts key by key on league issue #45: **identical on every shared field**,
including the per-sub-game rows, the audits and the standings block. imreeyal
recorded the verdict as `SETTLED`.

The superseding report is worth a sentence, because filing twice looks worse
than it is. Our first report carried `games_played_including_this
{best2934: 1, imreeyal: 5}` — we added the series to our own column and emitted
the opponent's declared count untouched, while the field is named *including
this*. **We found and disclosed it ourselves**, imreeyal ruled that the team
whose block was wrong re-files, and the corrected artifact carries a
`_supersedes` field naming the message it replaces. No game, score, winner,
audit or digest changed: `mutual_agreement.sha256` is identical in both.

### The friendly against gal-roy1

Six sub-games, settled 75–35 to us, audited both ways. **Not counted**, and not
claimed here: rule 37 declares the number of *counted* games, and
`counted_games_played()` reads the ledger of games both sides agreed to count —
not the artifacts on disk. Counting a warm-up would be a false declaration under
rule 38, which disqualifies the group that makes it.

**This is the one section no amount of engineering can fill.** It needs
opponents, and nothing in the codebase can produce one. One is now banked; the
second needs a second team to say yes.

**The minimum is 2, confirmed by the course staff on 2026-08-06.** The booklet
prose leaves it as an unfilled placeholder — `לפחות [ מינימום משחקים למעבר ] מול
קבוצות שונות`, in both places it appears — so we asked rather than guessed. It is
a **fixed** parameter (`קבוע 2`), not negotiable, and it was already correct in
our own config all along:

```json
"min_games_to_pass": 2      // config/<role>/game.json, and constants.MIN_GAMES_TO_PASS
```

An earlier draft of this file asserted "two" as our inference and then, when we
checked the source, retracted it as unknown. Both were right to write down: the
number is 2, and it was never something we could derive.

What *is* unambiguous in the rules, and what it costs us:

- The games must be against **different groups** (`קבוצות שונות`, plural).
- Rule 52 allows **exactly one counted game per opponent**, warm-ups unlimited.

Those two together mean one opponent can never satisfy the requirement — a
second counted game against the same team does not count twice. With the
minimum at 2, **both counted games are banked and the threshold is met.**

`imreeyal` and `gal-roy1` are both spent under rule 52, which leaves
`anrbj666` as the only pairing that could add a third counted game. They
answered in the end and have been the most demanding opponent of the three:
they found the sealed step-0 that never rode the wire, the counted ledger that
had drifted between our two repositories, and the reveals that reached them
unkeyable. A third counted game against them would be upside only — our counted
record is one tie and one loss, so a counted loss would leave the standing worse
than not playing at all.

**The honest position: the pass threshold is not met until a second team
agrees, and no amount of further engineering changes that.** It is recorded here
rather than smoothed over, because §3 is the section a reader checks first.

The "List of teams you played against" table wants, per game: date, start time,
end time, opponent team name, your score, their score, their declared number of
games, and the e-mail address their agent reported from. Every one of those is
recorded in the match artifacts (`artifacts/result_*.json` and
`artifacts/log_*.json`), so after each game the row can be transcribed rather
than remembered.

## 4. Self-assessed grade — the evidence

What the repository can honestly claim:

| Guidelines V3 gate | Required | Measured (2026-08-06) |
|---|---|---|
| Code lines per file | ≤ 150 | 0 of 140 files over; largest `test_handlers.py` at 150 |
| Test coverage | ≥ 85% | **93.6%**, 585 tests (thief repo: 93.3%, 583 plus 2 Gmail-extra skips) |
| Ruff violations | 0 | **0** |
| Dress rehearsal over sockets | — | Passes on both repos: four processes, both peers settled `capture`, each passed the other's audit |
| Dependency management | `uv` only | `uv.lock` committed, no `requirements.txt` |
| SDK layer | Required | `P2PChaseSDK`; no consumer bypasses it |
| Versioning from 1.00 | Required | Code, config and rate-limit versions declared and validated on load |
| Config-driven values | Required | Appendix F split into PERMANENT / TUNABLE and validated |
| Documentation set | PRD, PLAN, TODO | Present, plus six per-mechanism PRDs |
| Prompt book (§8.3) | Required | [PROMPTS.md](PROMPTS.md) — including the prompts that produced wrong answers |
| ISO/IEC 25010 | Required | Mapped in [PRD.md](PRD.md) |
| Appendix E, all 55 rules | Required | Mapped one by one in [COMPLIANCE.md](COMPLIANCE.md) |

Beyond the gates, and each backed by data in `results/`:

- A **working deception channel**, not a declared one: a compulsive liar is
  driven to 0.020 trust with 97% of its claims contradicted, against 0.724 for an
  honest opponent — measured over 30 seeds.
- A **measured** parameter decision rather than a reasoned one: 2400 sub-games of
  one-at-a-time sweep found `barrier_engage_range` = 4 losing six games in seven,
  and the winner was re-checked against five structurally different opponents and
  chosen on its worst case (ADR-012).
- **Stated limitations instead of hidden ones**: the drift reader falsely
  contradicts an honest opponent 30.7% of the time. It would have been easy to
  tune the learning rate until that number disappeared from the trust curve. It
  is documented instead, in four places.

### The number: 85

| If, at export | Recommend | Why |
|---|---|---|
| Two counted games, two different groups | **90** ← *the ceiling the table allows* | Every gate met with margin, the protocol proven against three independent implementations, and §3 answerable |
| At least one counted game | **85** ← *what we claim* | The build stands on its own and the league requirement is genuinely under way rather than untried |
| §3 is still `0` | **75** | A threshold requirement is unmet. Claiming a high number over an empty games table invites the reader to check, and they will |

**As of 2026-08-16 the top row is available: two counted games against two
different groups, both filed and cross-diffed with the opponent.** The operator
chose 85 on 2026-08-18 rather than the 90 the table allows. `fill_submission.py`
enforces the ceiling and not the claim -- it raises rather than print a number
above what the games table supports, and accepts any number below it, because
claiming less is never the direction a grader has to check.

Note what 90 does *not* rest on: our counted record is a tie and a loss, no
wins. The row is earned by the gates, the documentation and the protocol
working against three independent implementations — not by the scoreline.

**Why 85 and not 90**, which is the claim we are making. The engineering case is
strong enough for 90 on its own terms — every gate exceeded rather than met, an independent implementation's
fixtures reproduced with our own encoder, and corrections we filed against a
shared league kit accepted and merged into its spec. But §3 is a *threshold*
requirement, not a scored dimension, and 90 asserts the whole exercise was
completed. Claiming it while the games table is thin reads as a team that did
not check its own form.

**Why 85 and not 75.** 75 would describe a project that did not engage with the
league, and that is not what happened. Terms are fully agreed with `imreeyal` —
roles, scent model, tie rule, consensus signature, endpoints — and verified in
both directions against their published fixtures; two complete sub-games have
been played over the public internet against `gal-roy1` with clean mutual
audits. What is missing is opponents' availability in the last week, not
capability or effort.

**Do not write 85 over a `0`.** If the games table is still empty at export,
write 75. The three rows above are the argument the team can defend if asked,
and defending 85 requires a non-empty table.

Do not carry over the **90** from `best2934-ex01.pdf`. That was a different
exercise with a different scope, and reusing it would be a number nobody
re-derived — which is the failure this table exists to prevent.

What the team should *not* claim until it is true: league performance. Sections
3 and 4 of the form are separate questions, and a self-score that ignores an
empty game table will read as one that was not checked.

## 5. Before exporting the PDF

- [x] Push both repositories — done; both clean with nothing unpushed
- [x] `credentials.json` and `token.json` absent from both repos **and from
      their history** (rules 39–40) — verified across all branches, 0 hits
- [x] `.env` holds `P2PCHASE_SIGNING_SECRET` and is git-ignored in both repos,
      so the step-0 declaration is signed rather than falling back to an unkeyed
      digest (rule 24)
- [x] Confirm both repository URLs load while signed out — done 2026-08-06,
      both HTTP 200 unauthenticated
- [x] Authorise the Gmail sender and **prove which account it sends from** —
      done 2026-08-07. Send-only scope, and a live self-test came back labelled
      `SENT` *and* `INBOX`, which one mailbox only gets when it addressed
      itself. The sender is `eyalkol2@gmail.com`, the same address §1 declares
- [x] Ask the course staff for the **counted-game minimum** — answered
      2026-08-06: it is **2**, fixed and non-negotiable
- [ ] Play counted games against **2 different teams** (rule 52 caps counted
      games at one per opponent, so 2 teams is structural, not optional).
      **1 of 2 done**: `imreeyal`, 2026-08-15, 47–47 tie, filed and cross-diffed
      — that pairing is now spent. The second must come from `gal-roy1`, who
      have been offered both a designation of the settled friendly and a fresh
      series; `anrbj666` have not answered six messages
- [ ] Annotated tag on both: `git tag -a v1.0-submission -m "…" && git push
      origin v1.0-submission` (rule 41) — after the last counted game
- [ ] Copy the six personal-data values from `best2934-ex01.pdf` into the
      `.docx` (§2) — they are deliberately not in this repository
- [ ] Attach the match artifacts for every counted game
- [ ] Export to PDF and submit **once per member** in Moodle
