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
| Recommendation for self-scoring for the group | **[OPERATOR]** — must be agreed by all three members. §4 sets out the evidence and a proposed number to argue from, rather than leaving it blank |
| Cop repository url | `https://github.com/Krayz1a/best2934-cop` |
| Thief repository url | `https://github.com/Krayz1a/best2934-thief` |
| AI Agent email address that sent the results to the lecturer | **[OPERATOR]** — the Gmail account authorised in [GMAIL_SETUP.md](GMAIL_SETUP.md). Results go **to** `rmisegal+uoh26finalgame@gmail.com`; this field is the address they arrive **from** |

## 2. Members

The template prints two student blocks. The team has three, so **add a "Student
3" block** with the same five fields before filling it in.

| # | First / Last (English) | Hebrew | ID card |
|---|---|---|---|
| 1 | Tomer Levy | **[OPERATOR]** | **[OPERATOR]** |
| 2 | Eyal Koloshi | **[OPERATOR]** | **[OPERATOR]** |
| 3 | Alon Issman | **[OPERATOR]** | **[OPERATOR]** |

ID numbers and Hebrew spellings are personal data and stay out of this file on
purpose. **This repository is public**, so anything written here is published to
everyone, permanently and irrevocably — a git history cannot be un-pushed. Three
national ID numbers in a public repository would be a disclosure the form never
asked for, and two of the three belong to people who are not the person filling
it in.

They do not need to be retyped from memory. **Every value is already filled in
on `best2934-ex01.pdf`** — same group, same three members, questions 4, 5 and
"Student 3": English names, Hebrew names and ID cards. That file sits beside the
repositories and is not tracked by either. Copy the six values straight from it
into the `.docx`.

## 3. Games played

| Template field | Answer today |
|---|---|
| Legal number of games your agent emailed the instructor about | **0** |
| Maximum number of points accumulated | **0** |
| Games won / lost / drawn | 0 / 0 / 0 |
| Bonus eligibility | Not yet — the bonus needs counted games |
| Opponents with a working protocol | **1** (`gal-roy1`) |
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

**Correction to an earlier draft of this file.** It stated the requirement as
"at least two counted games against two different teams". The *two* was our
inference, not the rule. The booklet leaves the number as an unfilled
placeholder, in both places it appears (ch9, and the closing checklist):

> הפעלה תקינה של לפחות **[ מינימום משחקים למעבר ]** מול קבוצות שונות

— "proper operation of at least **[ minimum games to pass ]** against different
groups". The upper bound is blank the same way: "**[ מספר המשחקים המרבי לכל
קבוצה ]**". So the target is genuinely unknown to us and **must be asked of the
course staff**; writing a number here that we guessed would be the same class of
error as a self-score that was never checked.

What *is* unambiguous in the rules, and what it costs us:

- The games must be against **different groups** (`קבוצות שונות`, plural).
- Rule 52 allows **exactly one counted game per opponent**, warm-ups unlimited.

Those two together mean one opponent can never satisfy the requirement, whatever
the missing number turns out to be — a second counted game against the same team
does not count twice. We currently have **one** opponent, `gal-roy1`, with whom
the protocol is working end to end. At least one more team is required, and
recruiting one is the single longest pole in the project.

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
| Code lines per file | ≤ 150 | 0 of 136 files over; largest `test_handlers.py` at 150 |
| Test coverage | ≥ 85% | **93.3%**, 542 tests (thief repo: 93.1%, 540 plus 2 Gmail-extra skips) |
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

### A number to argue from

The grade is the team's to agree and this file cannot agree it for you. What it
can do is stop the discussion starting from nothing:

| If, at submission | Proposed recommendation | Why |
|---|---|---|
| The counted-game minimum is met | **90** | Every engineering gate is met with margin, the protocol is proven against an independent implementation, and §3 is answerable |
| Counted games exist but fall short of the minimum | **80–85** | The build stands on its own; the league requirement does not, and the form asks about both |
| §3 is still `0` | **70–75** | A threshold requirement is unmet. Claiming a high number over an empty game table invites the reader to check, and they will |

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
- [ ] Confirm both repository URLs load while signed out; a private repo the
      grader cannot open scores as an absent one
- [ ] Ask the course staff for the **counted-game minimum** — see §3; the
      booklet leaves it as a placeholder and it decides whether the project
      passes
- [ ] Recruit at least one opponent besides `gal-roy1` (rule 52 caps counted
      games at one per opponent, so a second team is structural, not optional)
- [ ] Annotated tag on both: `git tag -a v1.0-submission -m "…" && git push
      origin v1.0-submission` (rule 41) — after the last counted game
- [ ] Copy the six personal-data values from `best2934-ex01.pdf` into the
      `.docx` (§2) — they are deliberately not in this repository
- [ ] Attach the match artifacts for every counted game
- [ ] Export to PDF and submit **once per member** in Moodle
