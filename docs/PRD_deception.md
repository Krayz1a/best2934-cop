# PRD — The Deception Channel: Lying, Decoding and Detection

**Modules** `src/p2pchase/strategy/hint_decoder.py`,
`src/p2pchase/domain/thief_brain.py`, `src/p2pchase/runtime/match_side.py`
**Booklet** ch6.5 · **Rules** 25, 26, 27 · **Version** 1.00

---

## 1. Background

Each turn, an agent sends the opponent one sentence of at most fifteen words.
The rules explicitly permit that sentence to be false, and the truth/lie
`intent` flag is sealed in the commitment so it becomes checkable only at the
final audit.

This creates a small, genuine game of cheap talk. A signal that is free to send
and free to falsify carries information only when the receiver can *sometimes*
verify it — and the verifier here is physics: the pheromone trail, which cannot
be faked.

### 1.1 The distinction the whole mechanism rests on

At `REVEAL` an agent discloses two things:

| Disclosed | Can it lie? |
|---|---|
| The **move** | **No.** It is sealed in the commitment; changing it fails the audit |
| The **hint** | **Yes.** Free text, asserting whatever the agent chooses |

Cross-examining the move would therefore be pointless — it can only ever confirm
honesty. The hint is the channel deception actually travels on, so the hint is
what gets decoded and scored.

> **This was the project's most consequential bug.** The original implementation
> cross-examined the revealed move. The consequence was silent: the trust
> estimator sat pinned at its 0.90 ceiling in every match, the `intent = lie`
> flag changed nothing observable, and a compulsive liar was indistinguishable
> from an honest opponent. Every test passed. It was found only when a test was
> written that *forced* trust to collapse, and it did not.

---

## 2. Requirements

| ID | Requirement |
|---|---|
| D-1 | The sealed move is always truthful; only the sentence may deceive |
| D-2 | A lying hint asserts the reverse of the heading actually taken |
| D-3 | The receiver decodes a compass direction out of free-form English |
| D-4 | A compound bearing ("north-east") is refused, not guessed |
| D-5 | An unparsable hint is uninformative, not dishonest — it must not be scored |
| D-6 | A claim is judged only after the trail it must agree with has been sampled |
| D-7 | The local harness and the networked session share one implementation |
| D-8 | Deception is rationed: lie when it pays, tell the truth otherwise |
| D-9 | The LLM composes the sentence but never decides the move (rule 25) |

### 2.1 Input / output

| Operation | Input | Output |
|---|---|---|
| `heading_from_hint(hint)` | Free text | `"N"`/`"S"`/`"E"`/`"W"`/`"STAY"`/`None` |
| `opposite(move)` | A move | The reverse heading a liar would name |
| `Decision.spoken_heading` | — | `claimed_heading` when lying, `move` otherwise |
| `record_claim(state, hint)` | Received hint | Stores `pending_claim`; returns the decoded heading |
| `judge_claim(state)` | — | `True` / `False` / `None`; updates trust and belief |

---

## 3. Design

### 3.1 The sender: rationed deception

```
lie  ⟺  distance(us, believed cop) ≤ bluff_range   and   turn ≡ 0 (mod bluff_period)
```

Deception has to be spent, not sprayed. The opponent runs the same cross-check we
do, so a thief that lies every turn simply trains the cop to ignore it — and a
hint nobody believes is worth nothing when one is finally needed.

The measurements bear this out. Over seeds 7, 11 and 23, the cop's trust in the
thief settles at:

| Thief policy | Trust | Claims contradicted |
|---|---|---|
| Lies every turn | **0.020** (the floor) | 16/16, 13/13, 16/16 |
| Never lies | **0.593 – 0.597** | ~7/20 (measurement noise) |
| Shipped, rationed | **0.546 – 0.554** | ~9/20 |

A compulsive liar destroys its own channel within a handful of turns. The
rationed thief keeps a channel worth roughly as much as an honest one while still
getting its misdirection in.

### 3.2 The sentence

A lie names `opposite(move)` — the exact reverse of the heading taken. Among all
false claims, the reverse is the one most likely to cost a pursuer a turn: it
sends them the maximum distance away from the truth per unit of belief moved.

The sentence itself is composed by the talk provider (template, Ollama, Claude
API, or Claude CLI) from a heading and a landmark. The provider never sees the
board and never chooses the direction; it is handed `spoken_heading` and writes
around it.

### 3.3 The receiver: decode, then wait, then judge

Decoding is deliberately forgiving. It scans for a compass word anywhere in the
sentence and gives up quietly when there is none — because a hint we cannot parse
is a *normal* outcome, not an error, and treating it as dishonest would let an
opponent silence our estimator simply by writing prettier sentences.

Compound bearings are refused outright. "North-east" is consistent with two legal
moves, and a claim that cannot be checked must not be scored; guessing would
convict an honest opponent half the time.

Judgement is **two-phase**, and the split is not bookkeeping convenience:

```
reveal arrives   →  record_claim()   # nothing to check it against yet
scent sampled    →  judge_claim()    # now the evidence exists
```

At the moment a hint arrives, the opponent's scent for that same move has not
been sampled. Judging then would compare the claim against a stale trail. This is
the order in which the evidence actually becomes available, and both the local
harness and the networked `PeerSession` follow it through the same two functions
— so a strategy tuned in rehearsal behaves identically in a real match.

### 3.4 The verdict

```
observed = displacement_heading(previous centroid, current centroid)
honest   = (claimed == observed)
```

with `None` — no trust change at all — when either side of that comparison is
missing. A claim that survives moves belief; one that is caught contradicting the
record earns a trust penalty and nothing else.

---

## 4. Performance

| Metric | Target | Measured |
|---|---|---|
| Decode cost | negligible | two regex scans |
| Detection of a compulsive liar | trust ≤ 0.10 within a sub-game | 0.020, every claim contradicted |
| False conviction of an honest opponent | trust ≥ 0.50 | 0.593 |
| Separation, liar vs honest | > 0.30 | **0.573** |
| Token cost of the channel | 0 with the default provider | 0 |

---

## 5. Constraints and limitations

- **~20% false-contradiction rate against an honest opponent**, inherited from
  the drift reader's noise. This is why honest trust settles near 0.59 rather
  than at the ceiling. It is a truthful reflection of measurement uncertainty,
  and the separation from a liar remains decisive.
- **English compass words only.** An opponent writing in Hebrew, or using
  metaphor ("toward the river"), will produce unparsable hints — which degrade to
  "no claim", the safe outcome, rather than to a wrong verdict.
- **A sophisticated liar could lie perpendicular** rather than reversing, which
  is harder to catch. Not implemented on our side, and not defended against
  beyond the general trust decay. Noted as future work.
- **The `intent` flag is disclosed at final audit**, so after the sub-game an
  opponent can count exactly how often we lied. That is by design: it is the
  reputational cost that makes rationing rational.

---

## 6. Alternatives considered

| Alternative | Why rejected |
|---|---|
| Cross-examine the revealed move | It is sealed and therefore always truthful — the mechanism does nothing (§1.1) |
| Never lie | Forfeits a channel the rules explicitly provide, at zero cost to us |
| Always lie | Measured: destroys the channel's value within a few turns (trust 0.02) |
| Ignore incoming hints entirely | Discards free evidence, and an honest opponent's hints are worth ~0.59 trust |
| Parse with an LLM | Slow, non-deterministic, and rule 25 keeps model output out of decisions. Two regexes are deterministic and replayable |
| Treat an unparsable hint as a lie | Hands the opponent a trivial way to disable our estimator |

---

## 7. Success criteria and test scenarios

| Scenario | Expectation | Test |
|---|---|---|
| Compass word anywhere in a sentence | Decoded | `tests/unit/test_strategy/test_hint_decoder.py` |
| No direction named | `None`, no trust change | same |
| "north-east" | `None` — refused, not guessed | same |
| Two directions named | The first wins, as a reader would read it | same |
| Lying thief's decision | `claimed_heading == opposite(move)`; `move` untouched | `tests/integration/test_deception.py` |
| Full match, compulsive liar | Trust collapses; every claim contradicted | same |
| Full match, honest opponent | Trust stays above neutral | same |
| Liar vs truth-teller, same seed | Liar strictly less believed | same |
| Either policy | The commit chain still verifies — deception is a strategy, never an excuse | same |
