# Submission answer sheet

**Template** `uoh-rl07-final-project-2026.docx` · **Deadline** 2026-08-12 23:59
(no extensions) · **Last updated** 2026-08-06

This is the working copy of the Word form. Every field the codebase can answer is
answered here; everything else is marked **[OPERATOR]** with what it needs. Fill
the `.docx`, export to PDF, and submit it **individually in Moodle — one
submission per member**, not one for the group.

---

## 1. Header block

| Template field | Answer |
|---|---|
| Group ID code (8 characters, English, no spaces) | `best2934` |
| Recommendation for self-scoring for the group | **85** — see §4. Revise to **90** if two counted games are complete at export, or **75** if the games table is still `0`. Agree it between all three members before typing it |
| Cop repository url | `https://github.com/Krayz1a/best2934-cop` |
| Thief repository url | `https://github.com/Krayz1a/best2934-thief` |
| AI Agent email address that sent the results to the lecturer | `eyalkol2@gmail.com` — configured and wired; **the browser consent step is still outstanding**, see [GMAIL_SETUP.md](GMAIL_SETUP.md) §0. Results go **to** `rmisegal+uoh26finalgame@gmail.com`; this field is the address they arrive **from**, and it must match the account consent is granted with |

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
| Legal number of games your agent emailed the instructor about | **0** |
| Maximum number of points accumulated | **0** |
| Games won / lost / drawn | 0 / 0 / 0 |
| Bonus eligibility | Not yet — the bonus needs counted games |
| Opponents with a working protocol | **2** (`gal-roy1`; `imreeyal` agreed and conformance-verified, not yet played) |
| Counted games played | **0** — read from the ledger, not from the artifacts (rule 52) |

Two complete sub-games have been played against `gal-roy1` over the public
internet, both won by our cop by barrier capture at rounds 14 and 16, with the
mutual audit passing clean in both directions. **Neither was counted**, and
neither is claimed here: rule 37 declares the number of *counted* games, and
`counted_games_played()` reads the ledger of games both sides agreed to count —
not the artifacts on disk. Counting a warm-up would be a false declaration under
rule 38, which disqualifies the group that makes it.

**This is the one section no amount of engineering can fill.** It needs
opponents, and nothing in the codebase can produce one.

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
minimum at 2, we need **exactly one more team** than we have. We currently have
one, `gal-roy1`, with whom the protocol works end to end. `imreeyal` have now
agreed terms with us — roles, scent model, consensus signature and endpoints —
and a friendly window is being scheduled; `anrbj666` and `uoh-sqak` play the
same published forms, so the conformance work done for imreeyal carries to them.

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
| Two counted games, two different groups | **90** | Every gate met with margin, the protocol proven against an independent implementation, and §3 answerable |
| **At least one counted game** | **85** ← *the default* | The build stands on its own and the league requirement is genuinely under way rather than untried |
| §3 is still `0` | **75** | A threshold requirement is unmet. Claiming a high number over an empty games table invites the reader to check, and they will |

**Why 85 and not 90.** The engineering case is strong enough for 90 on its own
terms — every gate exceeded rather than met, an independent implementation's
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
- [x] Ask the course staff for the **counted-game minimum** — answered
      2026-08-06: it is **2**, fixed and non-negotiable
- [ ] Play counted games against **2 different teams** (rule 52 caps counted
      games at one per opponent, so 2 teams is structural, not optional).
      `gal-roy1` secured; `imreeyal` terms agreed and window being scheduled
- [ ] Annotated tag on both: `git tag -a v1.0-submission -m "…" && git push
      origin v1.0-submission` (rule 41) — after the last counted game
- [ ] Copy the six personal-data values from `best2934-ex01.pdf` into the
      `.docx` (§2) — they are deliberately not in this repository
- [ ] Attach the match artifacts for every counted game
- [ ] Export to PDF and submit **once per member** in Moodle
