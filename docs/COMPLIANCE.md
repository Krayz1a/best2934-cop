# Compliance matrix — Appendix E, all 55 mandatory rules

**Project** `best2934-cop` · **Booklet** v3.0.0, Appendix E (Tables 7–12) ·
**Version** 1.00 · **Last checked** 2026-08-05

Appendix E is the booklet's own checklist: five thematic tables plus the
cross-check additions, each rule carrying a sanction that runs from a technical
loss to disqualification. This document maps every one of them to the code that
satisfies it and the test that proves it, so the claim "we comply" is
falsifiable rather than asserted.

**Status legend** — **Met**: implemented and tested here. **Met, awaiting
play**: the mechanism is built and exercised against a loopback opponent; the
rule is only finally discharged during a real match. **Operator**: needs a
human, by design or by rule. **External**: depends on another team.

Summary: **45 Met · 4 Met, awaiting play · 4 Operator · 2 External**.

---

## 1. Network architecture, decentralisation and local epistemology (Table 7)

| # | Rule | Status | Where |
|---|---|---|---|
| 1 | Cop and thief run in two fully separate processes | Met | `p2pchase play` is one whole peer — it serves and calls over one session (ADR-015) — so a match is two processes, one per team. Proven end to end over sockets by `tools/rehearsal.py`. `local_match.py` is a rehearsal harness and is never used against a live opponent |
| 2 | No shared memory or variables between the sides | Met | `OwnState` has no attribute holding the opponent's position — enforced structurally, not by convention. `tests/integration/test_networked_sub_game.py` |
| 3 | The orchestrator is the single entry point to the subsystems | Met | `sdk/sdk.py` — every CLI command and every test goes through `P2PChaseSDK`. `tests/unit/test_cli/test_commands.py` stubs the SDK and the commands still behave |
| 4 | Game state managed by a standard state machine | Met | `domain/protocol.py` |
| 5 | Every illegal state transition is rejected | Met | `domain/protocol.py`; `tests/unit/test_mcp/test_handlers.py` |
| 6 | A deadline mechanism prevents stalling while waiting for the opponent | Met | `TurnDeadline` in `runtime/watchdog.py`, 30 s per message from the agreed config. Also from the other direction: `mcp/tool_guard.py` turns any escaping exception into a structured refusal, so a fault of ours cannot reach the opponent as an opaque transport failure and charge them a technical loss too (ADR-030). `tests/integration/test_live_transport.py::test_an_unexpected_fault_comes_back_as_an_answer_not_a_transport_error` |
| 7 | A watchdog monitors process failure and extracts data in a controlled way | Met | `Watchdog` in `runtime/watchdog.py` — fed only by `beat()` at the end of a completed step, so livelock trips it (ADR-011). `tests/unit/test_runtime/test_watchdog.py` |
| 8 | The live UI shows local truth only | Met | `ui/live_view.py`, `ui/board_render.py` — the renderers accept an `OwnState`, and no objective board exists to pass them |
| 9 | The full objective board is never displayed | Met | Same: satisfied by construction (P-3 in [PROMPTS.md](PROMPTS.md)) |
| 10 | A tunnel exposes the local server to the public internet | Operator | `play --host` binds loopback by default; publishing the port is ngrok/Localtonet's job. Nothing is exposed by accident |

## 2. Spatial mechanics, physics and board constraints (Table 8)

| # | Rule | Status | Where |
|---|---|---|---|
| 11 | The configuration file is byte-identical on both sides | Met | `config_sha256` over the canonical form; refused at handshake if it differs. `services/negotiation_service.py` |
| 12 | Minimum parameter values may be raised by agreement, never lowered | Met | `shared/config_schema.py` validates PERMANENT vs TUNABLE; `p2pchase check-config` reports every violation |
| 12b | Neither team keeps the easier half of the asymmetric scoring | Met | `domain/roles.py` — two order-independent conventions, both 3/3: `first_half` (cop = `sorted(group_ids)[0]` for sub-games 1-3) and `odd_even` (cop on 1/3/5), selected per opponent in `setup.json` because the rulebook assigns no roles and teams converged on different rules. Each is derived identically on both sides and `declare_step0` refuses a pairing that disagrees, naming the convention it judged against. This row previously cited a parity rule that was a function of *argument order*, so each peer made itself the cop in every odd sub-game and the two disagreed about all six (ADR-028). The citation is now a test that computes the assignment from both sides: `tests/unit/test_domain/test_roles.py::test_both_peers_derive_the_same_assignment_from_opposite_sides` |
| 13 | Movement is orthogonal only | Met | `domain/board.py` `legal_moves` |
| 14 | No diagonal moves | Met | `geometry.delta` raises `IllegalMoveError` naming the permanent move set. `tests/unit/test_domain/test_board.py` |
| 15 | Every barrier placement is declared openly | Met | `reveal_step` carries the barrier, declared from `pending_declaration()` and asserted to reach the opponent's board by `test_every_barrier_we_place_is_declared_and_reaches_the_opponents_board`. This row read "Met" for weeks while the networked peer sent `barrier: null` on every step — deriving the declaration from the sealed view broke when that shape changed (ADR-026). The citation is now a test that inspects the *receiver*, because a claim about a message is not a claim about its effect |
| 16 | No lying about where a barrier was placed | Met | The barrier is sealed in the SHA-256 commitment (rule 17); altering it fails the audit at that exact step |

## 3. Cryptography, log integrity and zero-knowledge (Table 9)

| # | Rule | Status | Where |
|---|---|---|---|
| 17 | Commit-reveal over SHA-256 | Met | `domain/crypto.py`; [PRD_commit_reveal.md](PRD_commit_reveal.md) |
| 18 | The nonce stays secret until the end of the game | Met | `final_reveal` is the only path that discloses nonces; `peer_session.final_reveal()` |
| 19 | Any hash mismatch at audit is a technical loss | Met | `audit_records` names the exact failing step; `p2pchase verify` exits non-zero. `tests/unit/test_domain/test_crypto.py` |
| 20 | A viewer application replays and verifies the log | Met | `ui/replay.py`, `p2pchase replay` / `verify`. Screenshots in README §9 |
| 21 | Truthful declaration on capturing the thief | Met | The cop attaches a `capture_claim` to every reveal, naming the only cell it can speak for honestly — its own, after moving (and the sealed cell when it drops a barrier, rule 46). `runtime/peer_session.py::capture_claim`, and the field is declared on the tool itself so it survives the wire (ADR-016) |
| 22 | No false capture claim | Met | The thief answers from its own true cell, and both the claim and the answer are sealed in the commit chain, so a false answer is provable at the audit. `tests/integration/test_network_artifacts.py::test_a_claim_on_the_wrong_cell_is_answered_honestly` |
| 23 | The scent emission model is cryptographically locked before play | Met | `kernel_fingerprint` over formula + kernel + a worked example, compared at handshake |
| 24 | A signed hardware declaration before play | Met | `reports/declaration.py` + `match_service.step_zero` — signed **and** committed as step 0, so editing it invalidates the chain. Now also *sent*: `runtime/peer_host.declare_step0` pushes it over MCP during the handshake, carrying the role we believe we hold (ADR-028). `tests/integration/test_network_artifacts.py::test_step_zero_is_the_first_record`, `tests/unit/test_runtime/test_step0_declaration.py` |

## 4. Strategy, language and the public network (Table 10)

| # | Rule | Status | Where |
|---|---|---|---|
| 25 | The LLM never decides the move (recommendation) | Met | `Decision` comes from `cop_brain`/`thief_brain`; the provider is handed `spoken_heading` and writes around it. ADR-003 |
| 26 | Communication in free natural language only | Met | `strategy/talk_providers.py`, `strategy/landmarks.py` |
| 27 | No direct numeric position protocol | Met | Asked of the model in the system prompt **and** enforced on the way out: `strip_positions` deletes digit-bearing and square-naming tokens from every hint, every provider. `tests/unit/test_strategy/test_talk.py` |
| 28 | A token-bucket rate limiter for Gmail reports | Met | `infra/rate_limiter.py` behind the Gatekeeper |
| 29 | A DoS detector protecting network resources | Met | `infra/gatekeeper.py` — DosDetector → QuotaManager → TokenBucket → OverflowQueue |
| 30 | Send-only Gmail scope | Met | `infra/gmail_sender.py`; [GMAIL_SETUP.md](GMAIL_SETUP.md) |

## 5. League fairness, procedure and competitive integrity (Table 11)

| # | Rule | Status | Where |
|---|---|---|---|
| 31 | Play the minimum number of games against different teams | External | **Minimum is 2**, confirmed by course staff 2026-08-06; a fixed parameter, already correct as `min_games_to_pass` in `config/<role>/game.json` and `constants.MIN_GAMES_TO_PASS`. The booklet prose leaves the number as an unfilled placeholder, so it was asked rather than derived. Rule 52 caps counted games at one per opponent, so 2 teams is structural. One secured (`gal-roy1`), two approached. [TODO.md](TODO.md) Phase 10 |
| 32 | Report results automatically by Gmail | Met, awaiting play | `services/reporting_service.py`; dry run is the default until credentials exist |
| 33 | The report is standard JSON | Met | `reports/result.py`; `tests/unit/test_reports/test_artifacts.py` |
| 34 | No free-text final report — JSON attachment only | Met | The body carries a summary and names the attachment as binding; the artifact is the JSON file |
| 35 | Both teams agree the result and each sends its own report | Met | `mutual_agreement.sha256` over `agreed_summary` — only the facts both peers derive from the same messages, so two honest reports hash identically and a disputed one does not (ADR-018). Two rehearsal peers produce the same digest; `tests/integration/test_ending_agreement.py` |
| 36 | Comprehensive mutual log audit at the end of every game | Met | `final_reveal` exchanges chains; each peer audits the other's. `tests/integration/test_networked_sub_game.py` |
| 37 | Declare the true number of games played at the start of each game | Met, awaiting play | `counted_games_played` in the `hello` reply — the interop surface only (`mcp/interop.py`), which is the one an opponent actually calls. Not in the native `hello` and **not** in the declaration artifact; this row previously claimed both, and neither was true. Read from the ledger of games *agreed to count* (rule 52), not from result files on disk: counting those declared two counted games against opponents we had invented while testing |
| 38 | No false declaration of games played | Operator | A rule about honesty, not a mechanism. The number is read from the artifacts on disk, so there is nothing to remember and nothing to round up |
| 39 | Never push secrets or credentials to the repository | Met | Verified over the **whole history**, not just the working tree: `git rev-list --all --objects` finds no credential file |
| 40 | Credentials and secrets are in `.gitignore` | Met | `.gitignore` lines 1–14, with the reason stated in the file |
| 41 | Tag the submitted version with a documented Git tag | Operator | `v1.0-submission`, annotated, after the last counted game — deliberately not applied early, so the tag marks what was actually submitted |
| 42 | A comprehensive academic report in the repository | Met | [README.md](../README.md) §1–§11 (model, dilemmas, strategy, screenshots, curves), [PRD.md](PRD.md), [PLAN.md](PLAN.md), six per-mechanism PRDs and the `assets/fig*.png` figures |
| 43 | Download the Moodle form, fill it, save as PDF, move no fields | Operator | Answers prepared in [SUBMISSION.md](SUBMISSION.md); the `.docx` itself must be filled by hand |
| 44 | Submit in Moodle individually, per member | Operator | Three submissions, one each |
| 45 | A unique eight-character group code | Met | `best2934` — validated on load, carried in every artifact |

## 6. Additions found when cross-checking the book (Table 12)

| # | Rule | Status | Where |
|---|---|---|---|
| 46 | A barrier placed on the thief's current cell is a capture | Met | Locally in `runtime/local_match.py::terminal_outcome`; over the wire the sealed barrier cell is what the cop claims |
| 47 | A thief with no legal move is captured | Met | `own_state.thief_is_boxed_in()`, checked on the thief's side because only the thief can see it — and then declared to the cop in `final_reveal`, which is what stops a won sub-game timing out into a technical loss for both (ADR-017). Depends entirely on rule 15 actually landing: the thief judges "no legal move" against *its own* board, so an undeclared wall makes this rule unfireable rather than merely inaccurate (ADR-026) |
| 48 | Score every ending by the score table (5/20, 10/5, 0/0) | Met | `domain/scoring.py`; `tests/unit/test_domain/test_scoring.py` |
| 49 | Two repositories, cross-linked in the READMEs, two links in Moodle, **four** links in both teams' JSON | Met | READMEs cross-link (§1.1 in both); `repositories` block in `reports/result.py` carries all four. `tests/integration/test_network_artifacts.py::test_the_result_carries_four_repository_links` |
| 50 | Each repository holds at least README, `config/`, PRD, PLAN and TODO | Met | All present in both repositories |
| 51 | Final reports go to the lecturer's agent address | Met | `constants.AGENT_REPORT_EMAIL` = `rmisegal+uoh26finalgame@gmail.com` — the final-project address, not assignment 06's |
| 52 | Exactly one counted game per opponent; warm-ups allowed | External | A procedural rule for the operator; the artifacts record which game was counted |
| 53 | The step-0 declaration records the commit hash that played | Met | `infra/sysinfo.git_commit()` in the declaration and per sub-game in the result. `tests/integration/test_network_artifacts.py::test_the_commit_hash_that_played_is_recorded` |
| 54 | The final JSON reports tokens consumed per sub-game and per series | Met | `tokens` per sub-game and `tokens_total_series` in `reports/result.py` |
| 55 | The self-assessed grade covers **code quality only**, not the league result | Met | Stated in [SUBMISSION.md](SUBMISSION.md) §4, where the evidence is gate measurements rather than match outcomes |

---

## What is genuinely not done

Three of these four need a human; the first needs another team. Listing them
plainly is more useful than a green table:

1. **No counted games yet** (31, 52, and the play-dependent half of 32, 35, 37).
   This is the only gap that can still cost the project a passing grade, and no
   amount of code closes it.
2. **The repositories are not tagged** (rule 41). Both are pushed and public;
   the annotated `v1.0-submission` tag waits for the last counted game, so it
   marks the code that actually played rather than the code that was ready.
3. **Gmail is in dry-run** (32) until the operator creates the OAuth client and
   runs the consent flow. The send path, the rate limiter and the DoS detector
   are all built and tested against a stub.
4. **The Moodle form and the per-member submissions** (43, 44) are clerical and
   must be done by the three members.
