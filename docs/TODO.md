# TODO — Tasks, phases and definitions of done

**Project** `best2934-cop` · **Document version** 1.00
**Last updated** 2026-08-04 · **Deadline** 2026-08-12 23:59 (no extensions)

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
| 3.2 | Every file ≤150 code lines | P0 | Team | Done | `tools/check_file_size.py` reports 0 over the limit across 102 files (largest: `board.py`, 148) |
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
| 6.5 | Test suite ≥85% coverage | P0 | Team | Done | 380 tests, 92.9% coverage, no test touching the network or a real API |

## Phase 7 — Documentation · **In progress**

| # | Task | Pri | Owner | Status | Definition of done |
|---|---|---|---|---|---|
| 7.1 | `docs/PRD.md` | P0 | AI | Done | Goals, KPIs, acceptance criteria, FR/NFR, user stories, milestones |
| 7.2 | `docs/PLAN.md` | P0 | TL | Done | C4 levels 1–4, UML, 12 ADRs with alternatives, API and data contracts |
| 7.3 | `docs/TODO.md` | P0 | EK | Done | This document |
| 7.4 | Per-mechanism PRDs | P0 | Team | Done | One each for belief, stigmergy, commit-reveal, deception, gatekeeper, protocol |
| 7.5 | Prompt book | P0 | Team | Done | `docs/PROMPTS.md` — context, prompts, outputs, iterations, lessons |
| 7.6 | `docs/GMAIL_SETUP.md` | P1 | AI | Done | A human can complete OAuth setup from it without guessing |
| 7.7 | README screenshots | P1 | TL | In progress | Terminal live view, replay verified, replay tampered — all captured from real program output. The Tkinter window shot needs `python3-tk` on the operator's machine and a manual capture; it is deliberately not faked |

## Phase 8 — Experiments · **Done**

| # | Task | Pri | Owner | Status | Definition of done |
|---|---|---|---|---|---|
| 8.1 | One-at-a-time parameter sweep | P1 | EK | Done | `tools/sweep.py`, 2400 sub-games, each tunable swept independently including its own default; raw data in `results/sweep.json` |
| 8.2 | Analysis notebook | P1 | EK | Done | `notebooks/analysis.ipynb` — every figure regenerated from `results/*.json`, LaTeX for the decay, likelihood and trust update rules |
| 8.3 | Token cost table | P1 | AI | Done | Measured, not estimated: 0 tokens for the whole experiment programme on the default template provider |
| 8.4 | Figures for the report | P1 | TL | Done | `assets/fig1_kernel.png` … `fig5_sweep.png` — kernel, belief entropy, trust collapse, robustness, sweep |
| 8.5 | Robustness check of the sweep winner | P1 | EK | Done | Winner re-measured against five structurally different thieves, 60 seeds each; selected by worst case (ADR-012) |
| 8.6 | Act on the finding | P0 | TL | Done | `barrier_engage_range` 4 → 1 in `config/police/setup.json`; capture rate 0.133 → 0.850 against the sweep thief |

## Phase 9 — Submission · **Not started**

| # | Task | Pri | Owner | Status | Definition of done |
|---|---|---|---|---|---|
| 9.1 | Push `best2934-cop` | P0 | Team | **Blocked** | Needs the operator's GitHub credentials — the agent cannot and must not hold them |
| 9.2 | Create and push `best2934-thief` | P0 | Team | Not started | Symmetric repo, cross-linked with the cop repo in both READMEs |
| 9.3 | Tag `v1.0-submission` on both | P0 | Team | Not started | Annotated tag (rule 41) |
| 9.4 | Fill the Word template → PDF | P0 | Team | Not started | Every mandatory section completed |
| 9.5 | Self-assessed grade | P0 | Team | Not started | Agreed by all three members |
| 9.6 | Individual Moodle submission | P0 | Team | Not started | Three submissions, one per member |

## Phase 10 — League play · **Blocked (external)**

| # | Task | Pri | Owner | Status | Definition of done |
|---|---|---|---|---|---|
| 10.1 | Recruit opponents on the course forum | P0 | Ext | Not started | At least two teams agree to play |
| 10.2 | Expose the MCP endpoint via tunnel | P0 | TL | Not started | Opponent reaches `hello` over the public internet |
| 10.3 | Play ≥2 counted games | P0 | Team | Blocked | Rule: minimum two games against *different* teams |
| 10.4 | Mutual audit + both-sides e-mail | P0 | Team | Blocked | Both teams report; the two result digests match (rule 35) |

---

## Blocked items and why

| Item | Blocked on | Note |
|---|---|---|
| 9.1 | Operator's GitHub credentials | The agent does not accept or enter tokens. Run `git push` yourself. |
| 5.3 (live) | Google Cloud OAuth client | A human must create the client and run the consent flow — see [GMAIL_SETUP.md](GMAIL_SETUP.md). Dry-run mode works today. |
| 10.x | Other teams | Nothing in the codebase can unblock this. |

## Known risks

| Risk | Impact | Mitigation |
|---|---|---|
| No opponent found before the deadline | Fails the two-game minimum | Start recruiting on the forum now; task 10.1 is the long pole |
| Public repository exposes strategy | Opponents can read the weights | Flagged twice; kept public by the team's explicit decision. Weights live in `setup.json` and can be changed between matches without touching code |
| Opponent implements Appendix F differently | Handshake refuses, no match | `check-config` and `handshake` let both sides compare fingerprints before agreeing to play |
| Trust estimator's 30.7% false-contradiction rate | Under-trusts an honest opponent (0.724, not the 0.90 ceiling) | Measured over 30 seeds and documented (ADR-006); the separation from a liar (0.020) remains decisive |
