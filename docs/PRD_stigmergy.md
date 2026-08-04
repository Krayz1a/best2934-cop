# PRD — Stigmergy: the Pheromone Trail

**Module** `src/p2pchase/domain/smell.py`, `src/p2pchase/domain/trail_reading.py`
**Booklet** ch4 · **Version** 1.00

---

## 1. Background

Stigmergy is indirect coordination through traces left in a shared environment —
the mechanism ants use to route around obstacles without any ant holding a map.
Here it is turned adversarial: each agent leaves a trail it cannot suppress, and
the opponent reads it.

This is the only channel in the game that **cannot be faked**. A hint is words; a
commitment is a hash; but scent is emitted by the act of moving. An agent's
options are to move (and be smelled somewhere new) or not move (and saturate its
current cell, which is worse).

### 1.1 The model

Emission at cell *c* adds a 5×5 kernel centred there. Every field then decays
once per full turn:

$$\tau_{t+1}(x) = \max\big(0,\; (1-\rho)\,\tau_t(x) + \Delta\tau_t(x)\big),
\qquad \rho = 0.10$$

The kernel is the literal table printed in booklet Figure 4:

| | | | | |
|---|---|---|---|---|
| 0.04 | 0.14 | 0.20 | 0.14 | 0.04 |
| 0.14 | 0.42 | 0.62 | 0.42 | 0.14 |
| 0.20 | 0.62 | **0.90** | 0.62 | 0.20 |
| 0.14 | 0.42 | 0.62 | 0.42 | 0.14 |
| 0.04 | 0.14 | 0.20 | 0.14 | 0.04 |

A Gaussian with σ² = 4/3 reproduces this table exactly except on the inner
diagonal, where it reads 0.43 against the book's 0.42 — a difference of exactly
0.01 on exactly four cells, `{(1,1), (1,3), (3,1), (3,3)}`. That is pinned in a
test as an equality rather than a tolerance, because it is a sharper claim.

Both forms ship. The literal table is the default so that two teams reading the
same figure hash identically; the closed form is offered for teams that prefer
it, and for board sizes where no printed table exists.

---

## 2. Requirements

| ID | Requirement |
|---|---|
| S-1 | Emission adds the kernel; overlapping emissions accumulate |
| S-2 | Decay is applied once per *full* turn, after both agents have moved |
| S-3 | Intensity never goes negative |
| S-4 | Cells below a floor are pruned, so a 35-step sub-game cannot grow the map without bound |
| S-5 | A peer samples only its **opponent's** field, never its own |
| S-6 | Over the network, a partial sample **merges** rather than replaces |
| S-7 | The emission-and-decay model is fingerprinted and exchanged before play (booklet ch4) |
| S-8 | The kernel size must be odd, so it has a centre |

### 2.1 Input / output

| Operation | Input | Output |
|---|---|---|
| `emit(cell)` | A cell | Kernel added around it |
| `decay_all()` | — | Every intensity multiplied by (1 − ρ); sub-floor cells pruned |
| `intensity(cell)` | A cell | Scalar τ, 0.0 if unrecorded |
| `centroid()` | — | Sub-cell (row, col) centre of mass, or `None` |
| `centre_of_mass()` | — | The same, snapped to a cell |
| `as_dict()` / `load(payload, merge)` | `{"r,c": τ}` | JSON-safe transport form |
| `kernel_fingerprint(kernel, ρ)` | Model | SHA-256 over formula + kernel + a worked example |

---

## 3. Reading a heading out of a trail

`trail_reading.displacement_heading` answers the question the lie detector needs:
*which way did the opponent actually go?*

It compares the **sub-cell centroid** of the opponent's field between two
samples and reports the dominant axis of the drift. Below a deadband of 0.02
cells it reports `None` — "no usable reading", which is deliberately not the same
as "the opponent stood still". From outside, those two are indistinguishable, and
claiming otherwise would put a false verdict into the trust estimator.

Only the dominant axis is reported: the board has no diagonal move, so a drift of
(0.30 south, 0.11 east) is one southward step seen through a lagging average, not
a diagonal one.

### 3.1 Why the centroid, and not the peak

Three readers were implemented and measured against ground truth over real
matches:

| Reader | Agreement with the true heading | Verdict |
|---|---|---|
| Half-plane scent mass around the peak | ~50%, and outvoted by the wrong direction on several turns | Rejected |
| Peak-cell displacement | Moves in integer jumps: reads "no movement" for several turns, then "impossible movement" | Rejected |
| **Sub-cell centroid drift** | **~80% on turns where the opponent moved** | **Adopted** |

The centroid moves a little every turn, in proportion to how much fresh scent was
laid down and where. Rounding it to a cell — as the original `centre_of_mass`
did — quantises away exactly the signal being measured, which is why `centroid()`
was added alongside it rather than replacing it.

---

## 4. Performance

| Metric | Target | Measured |
|---|---|---|
| Emission cost | O(k²), k = 5 | 25 cell updates |
| Map size after 35 steps | Bounded | ≤ 49 cells (pruning + board size) |
| Heading agreement, moving turns | > 70% | ~80% |
| Corroboration rate over *all* claims, honest opponent | — | 69.3% |
| Effect on posterior entropy | Substantial | 5.61 → **2.86 bits** |

---

## 5. Constraints and limitations

- **The reading lags.** It averages the whole accumulated trail, not just the
  latest emission, so a direction change takes a turn or two to register.
- **A stationary opponent still shows drift**, as old scent decays unevenly. The
  deadband suppresses most of this; the rest is absorbed by the trust estimator's
  small learning rate.
- **Over the network the sample is partial.** A peer asks about its top-12
  believed cells, so its centroid is computed over a subset. Merging (S-6) keeps
  earlier readings alive instead of discarding what was already paid for.
- ρ, the centre intensity and the grid size are all **PERMANENT** under Appendix F
  Table 16. Changing any of them disqualifies the team.

---

## 6. Alternatives considered

| Alternative | Why rejected |
|---|---|
| Uniform 3×3 emission | Loses the radial gradient, and the gradient is what makes a direction readable |
| No decay | The trail would saturate the board within ten turns and stop carrying information |
| Exponential decay per cell age | Requires per-cell timestamps and diverges between peers under packet loss; the global multiplier is reproducible |
| Sampling our own field too | Tells us nothing about the opponent and costs a round trip |
| Broadcasting the whole field each turn | Rejected as wasteful and as an information giveaway; the querying peer reveals only which cells interest it |

---

## 7. Success criteria and test scenarios

| Scenario | Expectation | Test |
|---|---|---|
| Emit at the centre | Centre reads 0.90, corners 0.04 | `tests/unit/test_domain/test_smell.py` |
| Emit near an edge | Kernel is clipped, no negative indices | same |
| Decay ten turns | Intensity ≈ τ₀·0.9¹⁰, never negative | same |
| Gaussian vs book table | Differ on exactly `{(1,1),(1,3),(3,1),(3,3)}` by exactly 0.01 | same |
| Even kernel size | Raises `ValueError` | same |
| Fingerprint | Identical models hash identically; a ρ change alters the hash | same |
| Partial network sample | Merges, does not erase earlier readings | `tests/integration/test_networked_sub_game.py` |
| Drift reader | Reports the dominant axis; `None` under the deadband | `tests/unit/test_domain/test_trail_reading.py` |
| Diagonal drift | Resolves to the larger component, never a diagonal | same |
| First sample of a match | No reading — nothing to compare against | same |
