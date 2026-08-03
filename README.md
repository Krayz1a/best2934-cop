# best2934 — Cops and Robbers over a peer-to-peer network

**Final project · Orchestration of AI Agents (2026) · University of Haifa**
Group code **best2934** — Tomer Levy, Eyal Koloshi, Alon Issman

| | |
|---|---|
| Cop repository | https://github.com/Krayz1a/best2934-cop |
| Thief repository | https://github.com/Krayz1a/best2934-thief |
| Booklet version implemented | 3.0.0 |
| Code version | 1.00 |
| Artifact schema version | 1.1 |

Two autonomous agents chase each other across a 7×7 grid. There is no server in
the middle, no referee, and no shared memory. Each agent runs an MCP server and
an MCP client at the same time, holds only its own truth, and has to infer the
rest — from an unforgeable scent trail, from barriers its opponent declares, and
from sentences its opponent may be lying in.

---

## Table of contents

1. [What this is](#1-what-this-is)
2. [Installation](#2-installation)
3. [Usage](#3-usage)
4. [Configuration guide](#4-configuration-guide)
5. [The model: a Dec-POMDP](#5-the-model-a-dec-pomdp)
6. [Orchestration over FastMCP, and its dilemmas](#6-orchestration-over-fastmcp-and-its-dilemmas)
7. [Strategies implemented](#7-strategies-implemented)
8. [Learning: what we did and did not use](#8-learning-what-we-did-and-did-not-use)
9. [Screenshots](#9-screenshots)
10. [Architecture](#10-architecture)
11. [Quality gates](#11-quality-gates)
12. [Contributing](#12-contributing)
13. [License and credits](#13-license-and-credits)

---

## 1. What this is

The cop wins by catching the thief. The thief wins by surviving 35 steps. The
cop can permanently seal cells, but only by giving up its move that turn, and
only 14 times per sub-game — so every wall is a trade.

What makes it a research problem rather than a chase is that **neither agent can
see the other**. The information one side gets about the other is:

| Channel | Trustworthy? | Why |
|---|---|---|
| Declared barrier | Yes, exactly | Declaring truthfully is mandatory (rules 15, 16) |
| Revealed move | Yes, but thin | "North" is a direction, not a position |
| Sampled scent | Yes, but noisy | Physics, not testimony — it cannot be forged |
| Verbal hint | **No** | The opponent may lie, and ours does |

Integrity is not taken on trust either. Every step is sealed with a SHA-256
commitment before it is disclosed, and every nonce is published at the end so
the whole chain can be replayed. A single altered bit is provable.

---

## 2. Installation

### Requirements

- **Python 3.11+**
- **[uv](https://docs.astral.sh/uv/)** — the only supported package manager
- **`python3-tk`** *(optional)* — for the graphical live view. Terminal mode
  works without it.
- **A tunnel** *(for league matches only)* — [ngrok](https://ngrok.com) or
  [Localtonet](https://localtonet.com). Rule 10 requires a publicly reachable
  MCP endpoint; localhost is legal for development only.

### Step by step

```bash
# 1. Install uv (once, per machine)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Clone and install
git clone https://github.com/Krayz1a/best2934-cop.git
cd best2934-cop
uv sync                      # core dependencies
uv sync --all-extras         # plus Gmail, Anthropic and notebook support

# 3. Optional: the graphical live view (Debian / Ubuntu)
sudo apt install python3-tk

# 4. Environment
cp .env-example .env         # then fill in your own values
```

> `pip`, `python -m venv` and `virtualenv` are not supported. Everything runs
> through `uv run` (guidelines §8.4).

### Environment variables

All secrets come from the environment; none are ever read from a config file or
written to a log (rule 39). `.env` is git-ignored.

| Variable | Needed for | Notes |
|---|---|---|
| `ANTHROPIC_API_KEY` | `trash_talk.provider = "claude_api"` | Optional — the default costs zero tokens |
| `P2PCHASE_GMAIL_SENDER` | Result reporting | Your agent's Gmail address |
| `P2PCHASE_GMAIL_CREDENTIALS` | Result reporting | Path to the OAuth client file |
| `P2PCHASE_GMAIL_TOKEN` | Result reporting | Path the consent flow writes |
| `P2PCHASE_SIGNING_SECRET` | Step-0 declaration | Any high-entropy string |
| `P2PCHASE_ROOT` | Wheel installs | Only when the checkout is elsewhere |

### Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `FastMCP is not installed` | `uv sync` — the transport is a core dependency |
| `Tkinter is not installed` | `sudo apt install python3-tk`, or use `--text` |
| `missing private setup file` | You are pointing at the wrong `--config-dir` |
| `the agreed configuration violates Appendix F` | A permanent parameter was changed or a minimum lowered. Run `check-config` — it names every offending key |
| `no OAuth token at token.json` | Run `uv run p2pchase authorize-gmail` once, in a browser |
| `handshake REFUSED: config_sha256 mismatch` | You and your opponent hold different `game.json` files. They must be byte-identical (rule 11) |

---

## 3. Usage

### Verify the installation

```bash
uv run p2pchase check-config --role police
uv run pytest
```

### Play a full local series (no opponent needed)

```bash
uv run p2pchase local-match --opponent rival42 --sub-games 6 --seed 7
```

Writes all four mandatory artifacts to `artifacts/`: one declaration, one config
and one log per sub-game, and one result report.

### Verify and audit logs

```bash
uv run p2pchase verify --log artifacts/log_best2934-vs-rival42_g01.json
uv run p2pchase audit  artifacts/log_*.json         # rule 36, mutual audit
```

Both exit non-zero on a verification failure, so they work as CI gates.

### Watch the belief map

```bash
uv run p2pchase gui --role police            # Tkinter heat map
uv run p2pchase gui --role police --text     # terminal, no Tkinter needed
```

### Play a real match against another team

Two processes, two terminals — that is the requirement, not a convention
(rules 1, 2).

```bash
# Terminal 1 — our peer's server
uv run p2pchase serve --role police --game-id best2934-vs-rival42 --port 8801

# Terminal 2 — our peer's client, driving the turn loop
uv run p2pchase play  --role police --game-id best2934-vs-rival42 \
                      --opponent-url https://their-tunnel.ngrok.io/mcp
```

For a league match, expose port 8801 through your tunnel and put the public URL
in `network.public_url`.

### Report the result

```bash
uv run p2pchase authorize-gmail                       # once, in a browser
uv run p2pchase send-report --result artifacts/result_<game>.json          # dry run
uv run p2pchase send-report --result artifacts/result_<game>.json --live   # sends
```

The report goes to `rmisegal+uoh26finalgame@gmail.com` as an **attached JSON
file** — never as body text, which would be rejected and score zero (rule 34).
The recipient is forced at load time and cannot be redirected by editing a
config file.

### Typical workflow

```
check-config → agree game.json with the opponent → handshake → serve + play
            → verify (own logs) → audit (their logs) → send-report --live
```

---

## 4. Configuration guide

Four files, and the split is deliberate.

| File | Shared? | Purpose |
|---|---|---|
| `config/<role>/game.json` | **Yes, byte-identical** | The agreed physics. Locked with `config_sha256` (rule 11) |
| `config/<role>/setup.json` | No | Ports, URLs, strategy weights, provider choice, identity |
| `config/rate_limits.json` | No | Gatekeeper limits, versioned separately |
| `config/logging_config.json` | No | Logging |

The decision test is one question: *must the opponent agree to this value, or
rely on it?* If yes it is shared; if no it stays private. A private file can
never weaken a signed term — the shared file overlays it, not the reverse.

### Parameters that matter

| Key | Default | Class | Effect |
|---|---|---|---|
| `board_and_agents.grid_size` | 7 | minimum | Larger boards favour the thief |
| `movement_and_barriers.max_barriers` | 14 | minimum | The cop's whole budget for shaping the arena |
| `movement_and_barriers.survival_threshold` | 35 | minimum | How long the thief must last |
| `pheromones.pheromone_decay` | 0.10 | **permanent** | How fast evidence goes stale |
| `pheromones.pheromone_kernel` | `book_table` | negotiable | `book_table` or `gaussian` — see below |
| `world.hint_max_words` | 15 | negotiable | Enforced locally, never left to the model |
| `strategy.*` | see `setup.json` | private | Tuning weights; measured in `notebooks/` |

`PERMANENT` parameters may not change at all — deviation disqualifies the team,
so the loader refuses to start rather than silently play an illegal match.
`MINIMUM` parameters may be raised by mutual agreement, never lowered.

### The scent kernel, and why it is fingerprinted

The pheromone field is the only unforgeable evidence in the game, which makes it
worthless unless both peers compute it *identically*. The booklet gives the 5×5
emission table as a figure. We reproduce that table literally
(`pheromone_kernel = "book_table"`) and also derive it from a Gaussian with
σ² = 4/3, which matches the figure everywhere to within 0.01 — except the
diagonal, where the closed form gives 0.43 against the figure's 0.42.

That one cell is exactly the kind of silent disagreement that would corrupt a
match without either side noticing, so the kernel and decay rate are hashed into
a `scent_fingerprint` and compared during the handshake. A mismatch stops the
match before move one.

---

## 5. The model: a Dec-POMDP

The game is a decentralised partially observable Markov decision process,
⟨I, S, {Aᵢ}, T, R, {Ωᵢ}, O, h⟩:

- **I** — two agents, cop and thief.
- **S** — the joint state: both positions, the barrier set, both scent fields,
  and the step counter. **No agent ever observes s ∈ S.**
- **Aᵢ** — `{N, S, E, W, STAY}` for both, plus barrier placement for the cop,
  purchasable only by choosing `STAY`.
- **T** — deterministic given joint actions; barriers make it non-stationary,
  since the reachable set shrinks as the match proceeds.
- **Ωᵢ** — what an agent actually receives: its own position, the declared
  barriers, sampled scent intensities, a revealed direction, and a ≤15-word
  sentence of unknown veracity.
- **O** — the observation function, and the interesting part. Scent is a noisy
  but honest function of the opponent's recent trajectory; the hint is a
  channel the opponent controls and may corrupt at will.
- **R** — cop 20 / thief 5 on capture; cop 5 / thief 10 on survival; **0 to
  both** on a technical loss.

That last term is what makes the protocol part of the strategy. A technical loss
zeroes *both* sides, so there is no reward for stalling an opponent into a
timeout — and every deadline in this codebase exists because waiting politely
loses the game just as thoroughly as playing badly.

### The belief update

Each agent maintains a posterior `b(cell)` over where the opponent is
(`domain/belief.py`), updated in three stages per turn:

1. **Predict.** Diffuse over legal moves, plus a `STAY_PRIOR = 0.2` mass on
   standing still. Entropy rises.
2. **Scent.** Reweight by `exp(SCENT_SHARPNESS · τ(cell))` with
   `SCENT_SHARPNESS = 6.0`. Evidence, so entropy falls.
3. **Hint.** Reweight by `1 ± trust`, where `trust` is *learned* — see below.

### Cross-examining a liar

A hint cannot simply be believed or ignored. `score_hint` compares the claim
against the scent field: if the cells the claim implies carry a consistency
score ≥ 0.25 of the available trail mass, the claim is judged credible. Trust
then moves toward that verdict at `TRUST_LEARNING_RATE = 0.25`, bounded to
`[0.02, 0.90]`.

The bounds are the design. Trust never reaches 1.0, because an opponent that has
told the truth forty times running may be setting up the forty-first. It never
reaches 0.0 either, because a channel you have stopped listening to cannot be
used against its owner — and a liar who knows you have stopped listening is free.

---

## 6. Orchestration over FastMCP, and its dilemmas

Each agent is simultaneously an MCP **server** (exposing eleven tools) and an
MCP **client** (calling its opponent's). Symmetry is not aesthetic: an
asymmetric protocol would need one side trusted with sequencing, and there is
nobody to trust.

```
   Agent A                                     Agent B
┌──────────────┐                          ┌──────────────┐
│  MCP server  │◄──────── commit ─────────│  MCP client  │
│  (11 tools)  │───────── commit ────────►│              │
│              │◄──────── reveal ─────────│  MCP server  │
│  MCP client  │───────── reveal ────────►│  (11 tools)  │
└──────────────┘        sample scent      └──────────────┘
```

### Dilemma 1 — when to disclose the nonce

Revealing each nonce as its step is revealed would let each peer verify moves
immediately, which sounds strictly better. It is not: it also lets a dishonest
peer *wait* to see a verified move before committing its own. So nonces are
withheld until the sub-game ends and disclosed all at once (rule 18). We trade
per-step verification for the guarantee that neither side can ever act on
information the other has already proven.

### Dilemma 2 — refusal versus exception

A tool that raises reaches the opponent as an opaque transport failure, which
they cannot distinguish from our process crashing. Every handler therefore
returns `{"ok": false, "reason": ...}` instead. Since rule 6 charges *both*
teams for an unfinished sub-game, making our refusals diagnosable is in our own
interest, not a courtesy.

### Dilemma 3 — waiting versus aborting

Two clocks run. `TurnDeadline` (30s) bounds one message. `Watchdog` (60s)
measures *progress*, and is fed only when a step actually completes — because an
opponent that answers instantly with refusals never trips a per-message timeout
while the match goes nowhere. When either fires, we abort, tell the opponent
why, and take the technical loss rather than hang.

### Dilemma 4 — pull-based scent

Scent could be broadcast each turn. Instead a peer must *ask* about specific
cells (`sample_scent`). This keeps the trail evidence rather than a feed: you
learn only about cells you thought to ask about, and asking well is part of
playing well. It also bounds message size on a 7×7 board that a larger agreed
grid would otherwise blow up.

### Dilemma 5 — the model never moves

Rule 25 forbids the LLM from choosing moves, and it is the right rule. Move
selection is deterministic Python, fully inspectable and replayable. The model
touches only the taunt. A hallucinated illegal move is a technical loss, and no
amount of rhetorical quality is worth that risk.

---

## 7. Strategies implemented

### The cop — `domain/cop_brain.py`

Movement is greedy descent on **belief-weighted** distance, averaged over the
top six hypotheses rather than chasing the single peak — a flat posterior makes
peak-chasing oscillate. Ties break toward keeping our own escape routes open,
since the player building walls is also the player who can be trapped by them.

Barrier policy is where the thinking is. Greedy walling is actively bad: a
barrier can cut the cop off from the thief or hand the thief a fresh corridor.
A placement is accepted only when it

1. measurably shrinks the thief's reachable area (`barrier_min_gain`),
2. does not increase our own distance to the thief, and
3. is worth spending a unit of a finite resource *now* — barriers are held back
   until the thief is within `barrier_engage_range`, and
   `barrier_endgame_reserve` are kept for the final squeeze.

### The thief — `domain/thief_brain.py`

Maximising distance from the cop is a trap: it walks straight into corners,
which is exactly what barriers exploit. The dominant term is **reachable area**;
distance is a safety margin, not the goal. Inside `endgame_window` steps of
survival the objective flips to pure immediate safety.

**Deception is rationed.** The opponent runs the same scent-versus-claim
cross-check we do, so a thief that lies every turn simply trains the cop to
ignore it — and a hint nobody believes is worth nothing when you finally need
one. We lie only when the cop is within `bluff_range`, and only every
`bluff_period` turns. Credibility is a resource with a budget, like barriers.

### Extending

Both are extension points. Subclass `BrainBase`, override `_pick_move` (and
`_decide_move` for the cop), and point `strategy.brain` at
`your.module:YourClass`. The engine loads it by name; nothing else changes.

---

## 8. Learning: what we did and did not use

**We did not use reinforcement learning, and there are no learning curves.**
Saying so plainly is more useful than a plot of something we did not do.

Reasons: a match is 35 steps with 6 sub-games per opponent and a maximum of 10
opponents, so the on-policy sample budget is a few thousand transitions against
strategies we cannot observe in advance. Self-play would optimise against our own
thief and nobody else's. The heuristics above encode structure — reachable area,
resource budgeting, credibility management — that a policy learned from this
much data would not recover.

What we *do* learn online is the **trust weight** (§5), which is a genuine
adaptive estimator with a decision-theoretic justification rather than a fitted
policy, and the parameter sweep in `notebooks/` measures the strategy weights
empirically rather than by assertion.

---

## 9. Screenshots

### Live belief map

The agent's own view during a match — its cell, the declared barriers, and a
heat map of where it believes the opponent is. **The opponent's true position is
absent, because this process does not have it** (rules 8, 9).

![Live belief map](assets/live_view_belief_map.png)

Terminal renderer, for machines without Tkinter:

![Live belief map, terminal](assets/live_view_text.png)

### Replay verification

Every commitment recomputed against its disclosed nonce:

![Replay verified](assets/replay_verified_ok.png)

And the same log with one byte altered — tampering is provable, not suspected:

![Replay tampered](assets/replay_tampered.png)

---

## 10. Architecture

```
External consumers (CLI / GUI / tests)
              │
              ▼
        ┌───────────┐
        │    SDK    │   single entry point for ALL business logic
        └─────┬─────┘
              ▼
   ┌──────────────────────┐
   │  services/           │  match · verification · negotiation · reporting
   └──────────┬───────────┘
              ▼
   ┌──────────────────────┐   ┌──────────────────────┐
   │  domain/             │   │  runtime/            │
   │  board · smell       │   │  peer · peer_session │
   │  belief · crypto     │   │  local_match         │
   │  brains · scoring    │   │  watchdog            │
   └──────────┬───────────┘   └──────────┬───────────┘
              ▼                          ▼
   ┌──────────────────────┐   ┌──────────────────────┐
   │  infra/              │   │  mcp/                │
   │  gatekeeper · gmail  │   │  handlers · server   │
   │  sysinfo             │   │  client · contracts  │
   └──────────────────────┘   └──────────────────────┘
```

No consumer reaches past the SDK. Business logic in a presentation layer cannot
be tested without that layer and cannot be reused by the next one.

Full C4 diagrams, UML and the architecture decision records are in
[`docs/PLAN.md`](docs/PLAN.md). Per-mechanism specifications are in
`docs/PRD_*.md`.

---

## 11. Quality gates

```bash
uv run pytest                                   # tests, coverage ≥ 85%
uv run ruff check .                             # zero violations
uv run python tools/check_file_size.py src tests   # every file ≤ 150 code lines
```

| Gate | Threshold | Enforced by |
|---|---|---|
| Test coverage | ≥ 85% | `fail_under` in `pyproject.toml` |
| Lint | 0 violations | `ruff check` |
| File size | ≤ 150 code lines | `tools/check_file_size.py` |
| Secrets in tree | 0 | `.gitignore` + `.env-example` |
| Package manager | `uv` only | `uv.lock` committed |

---

## 12. Contributing

- Every file stays under 150 code lines. When one grows past it, **split it by
  responsibility** — never compress it to fit.
- Docstrings on every module, class and public function, explaining *why*
  rather than restating *what*.
- Tests alongside the code, covering the error path as well as the happy one.
- No configurable value hard-coded: it belongs in `config/`, with the constant
  in `constants.py` as the fallback default.
- No business logic in `cli/` or `ui/`. Those layers call the SDK.
- Conventional, descriptive commits. Every counted match records the commit that
  played it (rule 53), so history has to stay legible.

---

## 13. License and credits

Released under the [MIT License](LICENSE).

The rules, the binding parameter table and the four artifact schemas are defined
by the project booklet v3.0.0 by **Dr. Yoram Segal**, University of Haifa. The
booklet is his copyrighted work and is not distributed here. The reference
simulator at [rmisegal/Game-P2P-Cop-Chase](https://github.com/rmisegal/Game-P2P-Cop-Chase)
was read for its artifact schemas; no code was copied, and where the booklet and
that code disagree, the booklet governs.

Third-party library attributions are listed in [`LICENSE`](LICENSE).

**Companion repository:** the thief agent lives at
[Krayz1a/best2934-thief](https://github.com/Krayz1a/best2934-thief) and shares
this engine.
