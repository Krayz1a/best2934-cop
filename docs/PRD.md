# PRD — Distributed Cops-and-Robbers over a Peer-to-Peer Network

**Project** `best2934-cop` (paired with `best2934-thief`)
**Course** אורקסטרציה של סוכני AI 26 — final project
**Team** best2934 — Tomer Levy, Eyal Koloshi, Alon Issman
**Document version** 1.00 · **Code version** 1.0.0 · **Config schema** 1.2

---

## 1. Overview and context

Two autonomous agents play Cops-and-Robbers on a 7×7 grid. One pursues, one
evades. What makes this a distributed-systems problem rather than a game
exercise is what is *absent*: there is no server, no referee, no shared memory
and no objective board. Each agent runs in its own process, on its own machine,
and holds only its own local truth.

Neither agent can see where the other one is. Each maintains a *belief* — a
probability distribution over the opponent's position — and updates it from two
channels that differ sharply in trustworthiness:

| Channel | Forgeable? | What it carries |
|---|---|---|
| Declared barrier | No (rules 15, 16) | An exact cell. Hard fact. |
| Revealed move | No — sealed in a SHA-256 commitment | A direction, not a position |
| Sampled scent | No — physical, decaying | Noisy evidence of where they have been |
| Verbal hint | **Yes** — free text, explicitly allowed to lie | Whatever the opponent chooses to assert |

The absence of a referee creates an obvious temptation to cheat, and the project
answers it cryptographically rather than procedurally: every move is sealed in a
SHA-256 commitment before the opponent acts, and every nonce is disclosed after
the sub-game so both teams can replay each other's logs. Tampering is arithmetic
to detect, not a matter of opinion.

### 1.1 Problem statement

> Build an agent that plays competitively under partial observability, against an
> adversary that may lie, with no trusted third party to enforce the rules — and
> make the result independently verifiable by the opponent.

### 1.2 Audience

| Audience | What they need from this project |
|---|---|
| Course grader | Verifiable artifacts, working code, the documented reasoning behind it |
| Opposing teams | A reachable MCP endpoint, a byte-identical agreed config, an auditable log |
| The team | A codebase that can be tuned between league matches without breaking |

### 1.3 Theoretical framing

The game is a **Dec-POMDP** — a decentralised partially-observable Markov
decision process — ⟨I, S, {Aᵢ}, T, R, {Ωᵢ}, O, h⟩:

| Symbol | In this project |
|---|---|
| I | Two agents: cop, thief |
| S | Both positions, all barriers, both scent fields |
| Aᵢ | `{N, S, E, W, STAY}` (permanent), plus barrier placement for the cop |
| T | Deterministic movement; blocked moves are illegal, not stochastic |
| R | Appendix F Table 17 — capture 20/5, survival 5/10, tie 2, technical loss 0 |
| Ωᵢ | Declared barriers, revealed directions, sampled scent, verbal hints |
| O | Scent kernel + decay; hint credibility as a *learned* trust weight |
| h | 35 steps |

The defining property is that **no agent observes S**. Every decision is taken
against a belief, and the quality of that belief is where the match is won.

---

## 2. Goals, KPIs and acceptance criteria

### 2.1 Measurable goals

| # | Goal | Metric | Target | Status |
|---|---|---|---|---|
| G1 | Play a full match with no central component | Processes involved | Exactly 2, no third | Met |
| G2 | Make cheating detectable | Tampered-log detection rate | 100% | Met — asserted in tests |
| G3 | Beat a uniform prior on opponent position | Posterior entropy vs 5.61 bits | < 4.6 bits sustained | Met — **2.86 bits** (30 seeds) |
| G4 | Make lying cost the liar something | Trust separation, liar vs honest | > 0.3 | Met — **0.020 vs 0.724** (30 seeds) |
| G5 | Zero-token play must be possible | Series cost with `template` provider | 0 tokens | Met |
| G6 | Survive a hostile or dead opponent | Unbounded waits | 0 | Met — two clocks |
| G7 | Meet the software guidelines | Coverage / ruff / file size | ≥85% / 0 / ≤150 | Met — 93% / 0 / 0 |

### 2.2 Acceptance criteria

1. `uv run pytest tests/` passes with coverage ≥ 85%.
2. `uv run ruff check .` reports zero violations.
3. `uv run python tools/check_file_size.py src tools` reports zero files over 150
   code lines.
4. A local series writes all four artifact types, and every log it writes passes
   `uv run p2pchase verify`.
5. A deliberately altered log fails verification, naming the exact step.
6. Two peers complete a sub-game over MCP and each audits the other successfully.
7. `uv run p2pchase check-config` reports an Appendix F violation without
   crashing.

### 2.3 Non-goals

- Winning by out-spending: the default provider costs zero tokens by design.
- A shared game engine or authoritative board — that is the thing being avoided.
- Reinforcement learning. Rule 25 forbids the LLM deciding moves; the movement
  policy is deterministic Python so that a replayed log is explicable.
- A polished GUI. The live view exists to *evidence* the belief map, not to be a
  product.

---

## 3. Functional requirements

### FR-1 · Local truth only
Each peer holds its own `Board`, position, scent fields and belief. There is no
attribute anywhere holding the opponent's true cell. Rendering an objective board
would be an illegal information advantage (rules 8, 9).

### FR-2 · Commit-Reveal integrity
Every step is sealed as `SHA-256(canonical_json(payload) || nonce)` before the
opponent acts. Nonces are withheld until the end of the sub-game (rule 18). The
Step-0 hardware declaration is committed like any other step, not written raw.

### FR-3 · Mutual audit
After the sub-game each peer replays the other's disclosed chain and returns a
verdict. A mismatch is a technical loss scoring zero (rule 19), not a warning.

### FR-4 · Stigmergic scent
Movement emits a 5×5 Gaussian kernel; every field decays by ρ = 0.10 per full
turn. A peer samples only the *opponent's* field, never its own.

### FR-5 · Bayesian belief with learned trust
The posterior is diffused by the transition model, sharpened by scent, and
transported by a hint weighted by an adaptive trust coefficient bounded to
[0.02, 0.90].

### FR-6 · Deception, and its detection
The thief may lie about its heading. The move sealed in the commitment stays
truthful; only the sentence deceives. The receiver decodes the sentence and
cross-examines it against the observed drift of the scent trail.

### FR-7 · Peer-to-peer MCP transport
Each agent runs a FastMCP server *and* a client. Eleven tools; symmetric
protocol with no initiator.

### FR-8 · Bounded waiting
A per-message deadline (30 s) and a watchdog measuring *progress* (60 s). An
opponent that answers promptly while going nowhere still trips the watchdog.

### FR-9 · Gatekeeper on every outbound API call
`DosDetector → QuotaManager → TokenBucket → OverflowQueue`. Excess is queued with
backpressure, never silently dropped. There is no second path to the API.

### FR-10 · Four mandatory artifacts
Declaration, per-sub-game config, per-sub-game log, and result — all JSON, all
carrying `game_id` and `game_uid`.

### FR-11 · Autonomous reporting
The agent e-mails the result itself, as a JSON *attachment* (rule 34), through
send-only OAuth scope (rule 30).

### FR-12 · SDK as the single entry point
CLI and GUI parse and draw; they decide nothing. All logic is reached through
`P2PChaseSDK`.

---

## 4. Non-functional requirements

| ID | Requirement | How it is met |
|---|---|---|
| NFR-1 | A turn completes well within the 30 s deadline | Local decision ≈ 1 ms; the LLM touches only the hint |
| NFR-2 | No unbounded resource growth in a 35-step sub-game | Scent cells are pruned below a floor; belief renormalises |
| NFR-3 | Reproducibility | Seeded RNG; canonical JSON; `uv.lock` committed |
| NFR-4 | Secrets never reach the repository | `.gitignore` covers credentials/tokens; paths come from the environment |
| NFR-5 | Runs on a bare checkout | Transport and Tkinter are optional; their absence prints a sentence, not a traceback |
| NFR-6 | Every file ≤ 150 code lines | Enforced by `tools/check_file_size.py` |
| NFR-7 | Configuration-driven | No magic numbers; Appendix F values flow from `config/<role>/game.json` |

### 4.1 ISO/IEC 25010 mapping

| Characteristic | Evidence in this project |
|---|---|
| Functional suitability | 366 tests; acceptance criteria §2.2 |
| Performance efficiency | Zero-token default; token budget reported per sub-game |
| Compatibility | MCP contract of eleven tools; result-shape tolerance across FastMCP versions |
| Usability | `check-config` diagnoses rather than crashes; text renderer for headless use |
| Reliability | Two clocks; clean abort; Gatekeeper backpressure |
| Security | SHA-256 commit-reveal; send-only OAuth; no secret ever in config or log |
| Maintainability | SDK/services/domain/infra layering; ≤150 lines per file; 93% coverage |
| Portability | `uv` only; optional dependencies degrade gracefully |

---

## 5. User stories

- **As a grader**, I open a log file and can tell whether it was altered, without
  running the project — every commitment is a hash over its own payload.
- **As an opposing team**, I exchange fingerprints before the match and refuse to
  play if the agreed physics differ by a byte.
- **As the cop**, I sample the thief's trail and narrow a 49-cell prior to a
  handful of plausible cells.
- **As the thief**, I lie when a pursuer is close enough for misdirection to cost
  it a turn, and tell the truth otherwise so the channel stays worth listening to.
- **As a teammate**, I change one weight in `config/<role>/setup.json` and re-run
  the sweep without touching a line of code.

---

## 6. Assumptions, dependencies, constraints

**Assumptions**
- Both teams implement the same Appendix F parameter table.
- Each team can expose a public MCP endpoint through a tunnel (rule 10).
- Opponents may be adversarial in speech but will not attack the transport.

**Dependencies** — `fastmcp` (transport), `httpx`, optional `anthropic` /
`google-api-python-client`, `pytest` + `ruff` (dev). Python ≥ 3.11.

**Constraints**
- Appendix F PERMANENT values may not change at all (rule 12).
- The LLM may never decide a move (rule 25).
- Two processes, no shared memory (rules 1, 2).
- Deadline **12/08/2026 23:59**, no late submissions.

**Out of scope** — matchmaking, a league server, persistent cross-match learning,
mobile clients.

---

## 7. Milestones

| Phase | Deliverable | Status |
|---|---|---|
| M1 | Domain core: board, scent, belief, commit-reveal | Done |
| M2 | Artifacts, Gatekeeper, replay verifier | Done |
| M3 | Guidelines V3 restructure: SDK layer, file-size split, uv | Done |
| M4 | MCP transport, peer orchestrator, negotiation | Done |
| M5 | CLI, live belief view, Gmail reporting | Done |
| M6 | Deception channel + test suite to ≥85% coverage | Done |
| M7 | Documentation set (this document and its siblings) | In progress |
| M8 | Parameter sweep, analysis notebook, figures | Pending |
| M9 | `best2934-thief` repository, cross-linked | Built and committed; push blocked on credentials |
| M10 | ≥2 counted league games with mutual audit | Pending — needs opponents |

See [TODO.md](TODO.md) for task-level status and definitions of done.

---

## 8. Related documents

| Document | Covers |
|---|---|
| [PLAN.md](PLAN.md) | C4 diagrams, UML, ADRs, API contracts, data schemas |
| [TODO.md](TODO.md) | Task list, phases, owners, definitions of done |
| [PRD_belief_map.md](PRD_belief_map.md) | Bayesian posterior and the trust estimator |
| [PRD_stigmergy.md](PRD_stigmergy.md) | Pheromone kernel, decay, sampling |
| [PRD_commit_reveal.md](PRD_commit_reveal.md) | SHA-256 integrity and mutual audit |
| [PRD_deception.md](PRD_deception.md) | Lying, decoding and lie detection |
| [PRD_gatekeeper.md](PRD_gatekeeper.md) | Rate limiting, quota, queueing, retries |
| [PRD_p2p_protocol.md](PRD_p2p_protocol.md) | MCP tools, state machine, timeouts |
| [PROMPTS.md](PROMPTS.md) | Prompt book — how this was built with AI |
| [GMAIL_SETUP.md](GMAIL_SETUP.md) | One-time OAuth setup, done by a human |
