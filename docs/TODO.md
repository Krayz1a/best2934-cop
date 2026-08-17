# TODO — Tasks, phases and definitions of done

**Project** `best2934-cop` · **Document version** 1.01
**Last updated** 2026-08-17 · **Deadline** 2026-08-20 23:59

The deadline moved from 12/08 under the reserve-duty exception (Guidelines §8),
which is also why this group has three members: Alon Issman is in active
military reserve service, and the exception grants both the third member and
submission up to the final-project deadline.

Status values: **Done** · **In progress** · **Not started** · **Blocked**

Owners: **TL** Tomer Levy · **EK** Eyal Koloshi · **AI** Alon Issman ·
**Team** all three · **Ext** depends on someone outside the team.

---

## Phase 1 — Domain core · **Done**

| # | Task | Pri | Owner | Status | Definition of done |
|---|---|---|---|---|---|
| 1.1 | Board geometry, barriers, path search | P0 | TL | Done | `legal_moves`, `shortest_path_length`, `reachable_area` tested; illegal moves raise `IllegalMoveError` naming the permanent move set |
| 1.2 | Pheromone kernel and decay | P0 | EK | Done | 5×5 Gaussian σ²=4/3 reproduces booklet Figure 4 to within one cell class; the four inner-diagonal cells differ by exactly 0.01 and that is pinned in a test |
| 1.3 | Bayesian belief map | P0 | EK | Done | Diffusion, scent likelihood and normalisation tested; entropy falls well below the 5.61-bit uniform prior in a real match |
| 1.4 | Commit-Reveal over SHA-256 | P0 | AI | Done | `audit_records` verifies an intact chain and names the exact failing step on a tampered one |
| 1.5 | Cop and thief strategies | P0 | TL | Done | Both act only on the posterior; neither reads an opponent position, because none exists to read |

## Phase 2 — Artifacts and safety · **Done**

| # | Task | Pri | Owner | Status | Definition of done |
|---|---|---|---|---|---|
| 2.1 | Four JSON artifacts | P0 | AI | Done | Declaration, config, log, result written; all valid JSON carrying `game_id` and `game_uid` |
| 2.2 | Step-0 signed hardware declaration | P0 | AI | Done | Signed **and** committed as step 0; editing it invalidates the signature |
| 2.3 | Replay verifier | P0 | EK | Done | `Verified OK — N/N steps` on an intact log; `INTEGRITY FAILURE` naming the step on a tampered one |
| 2.4 | Gatekeeper | P0 | TL | Done | Every outbound API call passes through it; over-limit work queues with backpressure rather than being dropped |

## Phase 3 — Guidelines V3 compliance · **Done**

| # | Task | Pri | Owner | Status | Definition of done |
|---|---|---|---|---|---|
| 3.1 | `uv` only, `uv.lock` committed | P0 | Team | Done | No `requirements.txt`; `pyproject.toml` is the single source of truth |
| 3.2 | Every file ≤150 code lines | P0 | Team | Done | `tools/check_file_size.py` reports 0 over the limit across 105 files (largest: `board.py`, 148) |
| 3.3 | SDK layer | P0 | EK | Done | No consumer reaches past `P2PChaseSDK` |
| 3.4 | Zero ruff violations | P0 | Team | Done | `ruff check .` clean on `src`, `tests` and `tools` |
| 3.5 | Versioning from 1.00 | P1 | AI | Done | Code, config and rate-limit versions declared and validated on load |

## Phase 4 — Peer-to-peer transport · **Done**

| # | Task | Pri | Owner | Status | Definition of done |
|---|---|---|---|---|---|
| 4.1 | MCP server and client | P0 | TL | Done | 11 tools registered; the set exposed equals the set declared in the contract |
| 4.2 | Peer orchestrator | P0 | TL | Done | Two peers complete a sub-game concurrently over loopback with no deadlock |
| 4.3 | Pre-game negotiation | P0 | AI | Done | A one-byte config difference is refused with the mismatch named |
| 4.4 | Two clocks | P0 | EK | Done | Per-message deadline plus a watchdog fed only by completed steps |
| 4.5 | Mutual audit over the wire | P0 | AI | Done | Each peer audits the other's disclosed chain; a tampered record fails at the right step |
| 4.6 | Capture detection over the wire | P0 | TL | Done | The cop claims a cell, the thief answers truthfully, either answer ends the sub-game (ADR-013). Found while writing the compliance matrix: the networked path had only ever checked for survival |
| 4.7 | Artifacts from a live match | P0 | AI | Done | A networked sub-game writes declaration, config, log and result; the result is rebuilt from the logs, so a second sub-game extends it rather than replacing it |

## Phase 5 — Interfaces · **Done**

| # | Task | Pri | Owner | Status | Definition of done |
|---|---|---|---|---|---|
| 5.1 | CLI, 11 subcommands | P1 | EK | Done | `verify` exits non-zero on a tampered log, so it works in a CI gate |
| 5.2 | Live belief view | P1 | TL | Done | Renders local truth only; Tkinter and terminal renderers, the latter usable headless |
| 5.3 | Gmail reporting | P1 | AI | Done | Send-only scope; JSON attachment, never body text; dry run is the default |

## Phase 6 — Deception and testing · **Done**

| # | Task | Pri | Owner | Status | Definition of done |
|---|---|---|---|---|---|
| 6.1 | Decode the opponent's sentence | P0 | EK | Done | Compass word extracted; a compound bearing is refused rather than guessed |
| 6.2 | Read the true heading from the trail | P0 | EK | Done | Centroid-drift reader chosen over two measured alternatives (ADR-006) |
| 6.3 | Fix the belief update to transport mass | P0 | EK | Done | A credible "north" moves `trust`-weighted mass north (ADR-004) |
| 6.4 | Prove lie detection works | P0 | Team | Done | Compulsive liar → 0.020 trust, 97% of claims contradicted; honest → 0.724; measured over 30 seeds |
| 6.5 | Test suite ≥85% coverage | P0 | Team | Done | 393 tests, 93.7% coverage, no test touching the network or a real API |
| 6.6 | Enforce the coordinate ban (rule 27) | P0 | EK | Done | `strip_positions` deletes digit-bearing and square-naming tokens from every hint before it reaches the wire — the system prompt asks, this enforces (ADR-014) |

## Phase 7 — Documentation · **Done**

| # | Task | Pri | Owner | Status | Definition of done |
|---|---|---|---|---|---|
| 7.1 | `docs/PRD.md` | P0 | AI | Done | Goals, KPIs, acceptance criteria, FR/NFR, user stories, milestones |
| 7.2 | `docs/PLAN.md` | P0 | TL | Done | C4 levels 1–4, UML, 12 ADRs with alternatives, API and data contracts |
| 7.3 | `docs/TODO.md` | P0 | EK | Done | This document. Refreshed 17/08 — a plan that still claims a passed deadline and an unmet threshold is worse than no plan |
| 7.4 | Per-mechanism PRDs | P0 | Team | Done | One each for belief, stigmergy, commit-reveal, deception, gatekeeper, protocol |
| 7.5 | Prompt book | P0 | Team | Done | `docs/PROMPTS.md` — context, prompts, outputs, iterations, lessons |
| 7.6 | `docs/GMAIL_SETUP.md` | P1 | AI | Done | A human can complete OAuth setup from it without guessing |
| 7.8 | Compliance matrix, Appendix E | P0 | Team | Done | [COMPLIANCE.md](COMPLIANCE.md) — all 55 rules mapped to code and test, with the four that are genuinely not done listed plainly |
| 7.9 | Submission answer sheet | P0 | EK | Done | [SUBMISSION.md](SUBMISSION.md) — every field the repository can answer, the rest marked for the operator |
| 7.7 | README screenshots | P1 | TL | Done | All four captured from real program output, none mocked up. The Tkinter belief map is exported through Tk's own PostScript writer from the same `LiveView.draw()` the animated window uses — the compositor here refuses X11 screen grabs, and a hand-drawn picture of a belief map would be a claim about the program rather than evidence of it. Each repository shows its own role's view |

## Phase 8 — Experiments · **Done**

| # | Task | Pri | Owner | Status | Definition of done |
|---|---|---|---|---|---|
| 8.1 | One-at-a-time parameter sweep | P1 | EK | Done | `tools/sweep.py`, 2400 sub-games, each tunable swept independently including its own default; raw data in `results/sweep.json` |
| 8.2 | Analysis notebook | P1 | EK | Done | `notebooks/analysis.ipynb` — every figure regenerated from `results/*.json`, LaTeX for the decay, likelihood and trust update rules |
| 8.3 | Token cost table | P1 | AI | Done | Measured, not estimated: 0 tokens for the whole experiment programme on the default template provider |
| 8.4 | Figures for the report | P1 | TL | Done | `assets/fig1_kernel.png` … `fig5_sweep.png` — kernel, belief entropy, trust collapse, robustness, sweep |
| 8.5 | Robustness check of the sweep winner | P1 | EK | Done | Winner re-measured against five structurally different thieves, 60 seeds each; selected by worst case (ADR-012) |
| 8.6 | Act on the finding | P0 | TL | Done | `barrier_engage_range` 4 → 1 in `config/police/setup.json`; capture rate 0.133 → 0.850 against the sweep thief |

## Phase 9 — Submission · **In progress**

| # | Task | Pri | Owner | Status | Definition of done |
|---|---|---|---|---|---|
| 9.1 | Push `best2934-cop` | P0 | Team | Done | Pushed via `gh auth git-credential` per invocation, so no token is ever held or written to git config. Working tree clean, nothing unpushed |
| 9.2 | Create and push `best2934-thief` | P0 | Team | Done | Live at `https://github.com/Krayz1a/best2934-thief`, gates green (540 passed, 93.1%). Differs by one constant (`DEFAULT_ROLE`) plus config and README; cross-linked from both |
| 9.3 | Tag `v1.0-submission` on both | P0 | Team | Not started | Annotated tag (rule 41). Deliberately left until after the counted games, so the tag marks what was actually submitted |
| 9.4 | Fill the Word template → PDF | P0 | Team | **Done 2026-08-18** | Filled and read back field by field, then exported to PDF via LibreOffice and read back page by page: 2 counted games, max points 47, won 0 / lost 1 / drawn 1, bonus **No**, self-score **85**. Two cells blank pending `gal-roy1` (their declared count and agent e-mail, asked 17/08). Generated outside both repositories by a script that is not in either, because it carries three ID numbers |
| 9.5 | Self-assessed grade | P0 | Team | **Done 2026-08-18** | Operator claims **85**; the games table would allow 90 and `grade()` refuses anything above that ceiling, so the form cannot claim a number its own table contradicts. "Maximum points accumulated" resolved to the best single series (**47**, not the league total 62): the booklet uses "the accumulated score" for the sum of sub-games between a *pair* of teams, and "maximum" is only meaningful where several candidates exist -- a league total is one number |
| 9.6 | Individual Moodle submission | P0 | Team | Not started | Three submissions, one per member. Then delete the `.docx`, `fill_submission.py` and `SUBMISSION_FILL_IN.md` — all three carry ID numbers |
| 9.7 | Ask the staff for the counted-game minimum | P0 | Team | Done | Answered 2026-08-06: **2**, fixed and non-negotiable. Already correct as `min_games_to_pass` in our config; the booklet prose left it as a placeholder, so it had to be asked rather than derived |
| 9.8 | Document the tied-series scoring choice | P0 | Team | Done | The book and the reference contradict each other; the course grants academic freedom with a written justification. We ADD `tie_score` to the sums rather than replacing them — see README §4, "The tied-series scoring choice". Cost recorded: our tie digest with `gal-roy1` moved and they must recompute or object |

## Phase 10 — League play · **Threshold met: 2 counted games filed**

| # | Task | Pri | Owner | Status | Definition of done |
|---|---|---|---|---|---|
| 10.1 | Recruit opponents on the course forum | **P0** | Ext | **Done** | Three secured and played: `imreeyal`, `gal-roy1`, `anrbj666`. Rule 52 allows one counted game per opponent, so the first two are now **spent** and only `anrbj666` can still change the standing |
| 10.2 | Expose the MCP endpoint via tunnel | P0 | TL | Done | `https://monogram-radio-blooper.ngrok-free.dev/mcp`, a **reserved** domain so it survives restarts. Verified by a real `hello` from the public internet. Both roles serve it in turn via `tools/endpoint.py take`; `hello` publishes `role` so the wrong one cannot answer unnoticed |
| 10.3 | Play the counted games | P0 | Team | **Done — 2 of a minimum 2** | `imreeyal` 15/08, series **tied 47-47** over six sub-games. `gal-roy1` 16/08, **lost 15-30** over three. Both signed off by the operator before play and filed. A third against `anrbj666` would be upside only and needs the operator to say so: our counted record is one tie and one loss, so a counted loss there would make the standing worse than not playing |
| 10.4 | Mutual audit + both-sides e-mail | P0 | Team | Audit proven, e-mail live | Mutual audit has passed in both directions against three genuinely independent implementations. The Gmail client is authorised and confirmed by a live send; the corrected `imreeyal` result was filed through it |

## Phase 11 — Interoperability hardening · **Done**

Provoked entirely by opponents. Five of the six defects fixed here were found by
`anrbj666` reading our handshakes, not by our own suite — which is the finding,
and the reason this phase exists as a record rather than being folded into 4.

| # | Task | Pri | Owner | Status | Definition of done |
|---|---|---|---|---|---|
| 11.1 | Sealed step-0 on the reference-v3 wire (rule 53) | P0 | AI | Done | The record was always sealed and written as record 0 of our own log; nobody sent it. Their surface has no step-0 tool and `receive_control` is explicitly not part of the sealed record, so per the kit's log schema it now rides as the **first record of our final audit** |
| 11.2 | SPEC 7.2 pairing declaration | P0 | AI | Done | `sub_game_number` and `role` at the **top level** of the agreement, never inside `terms` — their `verify_peer` is an exact dict compare, so a field in `terms` would get every agreement refused instead of adding a gate |
| 11.3 | Our half of the 7.2 refusal | P0 | TL | Done | Their declared number compared against the window we opened. Silence is **not** a mismatch: a peer that does not implement 7.2 is quiet, not mispaired |
| 11.4 | One counted ledger, not one per repo | P0 | EK | Done | Moved from gitignored per-repository `artifacts/` to synced, committed `config/counted_games.json`. The two had drifted to 1 and 2, so every cop window under-declared us — a false declaration under rule 37 |
| 11.5 | The move ceiling is not a message to wait for | P0 | TL | Done | The thief's last move ends the sub-game, so there is no cop turn 35. We blocked on one and filed `technical_loss` for a game we had drawn — the outcome turned on whether their audit beat our 30s deadline |
| 11.6 | Prove it over a real socket | P0 | AI | Done | `tools/reference_rehearsal.py` stands a peer publishing their four tool names on a real port and drives the real `p2pchase play` at it. Found a seventh bug on its first clean run: our 7.2 `role` was `"THIEF"` where reference-v3 spells roles lowercase |

---

## Blocked items and why

| Item | Blocked on | Note |
|---|---|---|

| 9.4 (two cells) | `gal-roy1` | Their declared counted-game count and agent e-mail are theirs to declare, not ours to infer. Asked 17/08. A blank cell is better than a guess: rule 38 sanctions a false declaration. |
| 9.5, 9.6 | The three members | Nothing in the codebase can unblock these, and they are now the only things between a finished agent and a submitted project. |
| 10.3 (a third) | Operator | Deliberate. `anrbj666` is the one pairing rule 52 leaves, and a counted game there is **two-sided** — our record is one tie and one loss, so a counted loss would leave us worse off than not playing. Upside only, and the operator's call. |

## Known risks

| Risk | Impact | Mitigation |
|---|---|---|
| ~~Only one opponent found~~ | ~~Fails a threshold outright~~ | **Retired 16/08.** Three opponents played, two counted games filed against different groups. The threshold is met and banked |
| The three Moodle submissions do not happen | **Fails outright, and is not recoverable** | Now the highest risk on this list by a distance. Every code risk below is survivable; a missed deadline is not, and no amount of league play substitutes for it. Tasks 9.5 and 9.6 |
| A series is reported differently by the two teams | Rule 35 voids it **for both** | Our figures are posted to the opponent before filing so a disagreement surfaces while it can still be corrected. This is why the `gal-roy1` cells are blank rather than guessed |
| `barrier_stall_turns` is reported as validated | A claim the evidence does not support | It has **never fired on a wire**: 0 barriers in every police window played. Every capture came from a chase that closed monotonically, so the stall counter never reached three. Must be described as untested, not as working |
| Public repository exposes strategy | Opponents can read the weights | Flagged twice; kept public by the team's explicit decision. Weights live in `setup.json` and can be changed between matches without touching code |
| Opponent implements Appendix F differently | Handshake refuses, no match | `check-config` and `handshake` let both sides compare fingerprints before agreeing to play |
| Trust estimator's 30.7% false-contradiction rate | Under-trusts an honest opponent (0.724, not the 0.90 ceiling) | Measured over 30 seeds and documented (ADR-006); the separation from a liar (0.020) remains decisive |
