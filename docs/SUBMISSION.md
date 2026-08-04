# Submission answer sheet

**Template** `uoh-rl07-final-project-2026.docx` · **Deadline** 2026-08-12 23:59
(no extensions) · **Last updated** 2026-08-04

This is the working copy of the Word form. Every field the codebase can answer is
answered here; everything else is marked **[OPERATOR]** with what it needs. Fill
the `.docx`, export to PDF, and submit it **individually in Moodle — one
submission per member**, not one for the group.

---

## 1. Header block

| Template field | Answer |
|---|---|
| Group ID code (8 characters, English, no spaces) | `best2934` |
| Recommendation for self-scoring for the group | **[OPERATOR]** — see §4; must be agreed by all three members |
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

ID numbers and Hebrew spellings are personal data; they are deliberately not
stored in the repository and must be typed straight into the `.docx`.

## 3. Games played

| Template field | Answer today |
|---|---|
| Legal number of games your agent emailed the instructor about | **0** |
| Maximum number of points accumulated | **0** |
| Games won / lost / drawn | 0 / 0 / 0 |
| Bonus eligibility | Not yet — the bonus needs counted games |

**This is the one section no amount of engineering can fill.** The rules require
at least **two counted games against two *different* teams**, each one audited by
both sides and reported by both agents' e-mail. Nothing in the codebase can
unblock it: it needs opponents.

The "List of teams you played against" table wants, per game: date, start time,
end time, opponent team name, your score, their score, their declared number of
games, and the e-mail address their agent reported from. Every one of those is
recorded in the match artifacts (`artifacts/result_*.json` and
`artifacts/log_*.json`), so after each game the row can be transcribed rather
than remembered.

Recruit on the course forum now — this is the long pole, and it is the only task
with a hard external dependency.

## 4. Self-assessed grade — the evidence

The grade is the team's to choose. What the repository can honestly claim:

| Guidelines V3 gate | Required | Measured (2026-08-04) |
|---|---|---|
| Code lines per file | ≤ 150 | 0 of 105 files over; largest `board.py` at 148 |
| Test coverage | ≥ 85% | **93.73%**, 393 tests |
| Ruff violations | 0 | **0** |
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

What the team should *not* claim until it is true: league performance. Sections
3 and 4 of the form are separate questions, and a self-score that ignores an
empty game table will read as one that was not checked.

## 5. Before exporting the PDF

- [ ] `git push origin master` in **both** repositories (needs the operator's
      GitHub credentials — the agent will not hold them)
- [ ] Confirm both repository URLs load while signed out; a private repo the
      grader cannot open scores as an absent one
- [ ] Annotated tag on both: `git tag -a v1.0-submission -m "…" && git push
      origin v1.0-submission` (rule 41) — after the last counted game
- [ ] Check that `credentials.json` and `token.json` are absent from both repos
      **and from their history** (rules 39–40)
- [ ] Attach the match artifacts for every counted game
- [ ] Export to PDF and submit **once per member** in Moodle
