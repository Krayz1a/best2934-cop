# PRD — Bayesian Belief Map and the Adaptive Trust Estimator

**Module** `src/p2pchase/domain/belief.py` · **Booklet** ch1, ch4, ch6.4
**Version** 1.00

---

## 1. Background

Neither agent ever observes the world state. Booklet §6.4 is explicit: *"both
sides are entirely symmetric: neither of them sees the opponent's true
position."* Each therefore maintains

$$b_t(s) = P(\text{opponent occupies } s \mid o_{1:t})$$

a distribution over all 49 passable cells, updated by Bayes' rule from every
observation the protocol delivers.

This is the standard POMDP belief update, in two halves:

**Prediction** (the transition model). The opponent may stay put or step to any
passable orthogonal neighbour:

$$\bar b_{t+1}(s') = \sum_s b_t(s)\, T(s' \mid s), \qquad
T(s\mid s) = \pi_{\text{stay}},\quad
T(s'\mid s) = \frac{1-\pi_{\text{stay}}}{|N(s)|}$$

with `STAY_PRIOR` π_stay = 0.2. A boxed-in cell keeps all its mass.

**Correction** (the observation model), applied once per evidence channel:

$$b_{t+1}(s) \propto \bar b_{t+1}(s) \cdot P(o \mid s)$$

---

## 2. Requirements

| ID | Requirement |
|---|---|
| B-1 | The posterior sums to 1 after every update |
| B-2 | Belief starts as a point mass — start positions are agreed, so step 0 is certain |
| B-3 | A cell behind a barrier or off-board carries zero probability |
| B-4 | Belief may never die out entirely; total collapse resets to the uniform prior |
| B-5 | Scent evidence sharpens; silence does not zero a cell |
| B-6 | Hint evidence is weighted by a *learned* trust coefficient |
| B-7 | Trust is bounded strictly inside (0, 1) at both ends |
| B-8 | Every query is safe on an empty map (returns `None`, never raises) |

### 2.1 Input / output

| Operation | Input | Output |
|---|---|---|
| `predict()` | — | Diffused, renormalised posterior |
| `update_from_scent(scent)` | Opponent's `ScentMap` | Sharpened posterior |
| `update_from_hint(heading)` | `"N"`/`"S"`/`"E"`/`"W"`/`None` | Transported posterior |
| `score_claim(claimed, observed)` | Two headings | `True`/`False`/`None`, and a trust update |
| `entropy()` | — | Shannon entropy, bits |
| `top(n)` / `most_likely()` / `expected_cell()` | — | Ranked hypotheses |

---

## 3. The observation models

### 3.1 Scent likelihood — unforgeable, noisy

$$P(o_{\text{scent}} \mid s) \propto \exp\!\left(\kappa \cdot \frac{\tau(s)}{\max_x \tau(x)}\right),
\qquad \kappa = 6.0$$

Normalising by the peak makes the update invariant to how much total scent
happens to be on the board, which matters because the field decays.

Silence is treated as *absence of information*, not evidence of absence: a cell
with no reading gets `exp(0) = 1`, i.e. it is left alone rather than zeroed. An
opponent who has genuinely never visited a region would otherwise be able to
hide by standing still.

### 3.2 Hint transport — forgeable, trust-weighted

A directional claim is **not** evidence about which cell the opponent occupies.
It is evidence about how the whole cloud *moved*. With trust `t`:

$$b'(s \oplus d) \mathrel{+}= t \cdot b(s), \qquad b'(s) \mathrel{+}= (1-t)\cdot b(s)$$

where `s ⊕ d` is the neighbour in the claimed direction. Mass facing a wall stays
put rather than evaporating.

> **This replaced a mechanism that provably did nothing.** The original design
> built the set of cells "consistent with north" and boosted them by `(1 + t)`
> while damping the rest by `(1 − t)`. Once belief has diffused, almost every
> cell has a northern neighbour, so the claimed set covered the board and the two
> factors cancelled. See [PLAN.md](PLAN.md) ADR-004.

### 3.3 The trust estimator

Trust is a scalar the map *learns* from the opponent's track record:

$$t \leftarrow \operatorname{clip}\big(t + \alpha\,(y - t),\; t_{\min},\, t_{\max}\big),
\qquad y = \mathbb{1}[\text{claim matched the observed drift}]$$

| Constant | Value | Why |
|---|---|---|
| `TRUST_INITIAL` | 0.5 | Neutral: no prior reason to believe or disbelieve a stranger |
| `TRUST_LEARNING_RATE` α | 0.25 | One reading nudges; four consistent readings convict |
| `TRUST_FLOOR` | 0.02 | Never permanently deaf — a reformed liar can climb back |
| `TRUST_CEILING` | 0.90 | Never fully credulous — an opponent honest forty times may be setting up the forty-first |

`score_claim` returns `None` — and updates nothing — when there is no claim or no
readable drift. An unreadable turn is *not* evidence of honesty, and scoring it
as such would let an opponent silence the estimator by writing vaguer sentences.

---

## 4. Performance

| Metric | Target | Measured |
|---|---|---|
| Update cost per turn | < 1 ms | ~0.1 ms (49 cells) |
| Entropy against a live opponent | < 4.6 bits | ≈ 3.6 bits (uniform = 5.61) |
| Entropy with no opponent (solo) | ≈ uniform | 5.0–5.6 bits, as expected |
| Trust, compulsive liar | ≤ 0.10 | **0.020** across seeds 7, 11, 23 |
| Trust, honest opponent | ≥ 0.50 | **0.593–0.597** |
| Trust, rationed liar (shipped thief) | between | **0.546–0.554** |

The three-way separation is the headline result: the estimator discriminates, and
it does so without simply distrusting everyone.

---

## 5. Constraints and limitations

- **Small support.** 7×7 = 49 cells, so exact Bayesian updating is affordable. A
  particle filter would be needed at a much larger board size; it is not needed
  here and would add error for no benefit.
- **The drift reader is noisy.** It agrees with the true heading on ~80% of
  moving turns, so an honest opponent is falsely contradicted ~20% of the time.
  That is why honest trust settles near 0.59 rather than at the ceiling — an
  honest reflection of the measurement, not a bug.
- **Wall-adjacent bias.** Mass that cannot be transported stays put, which
  slightly over-weights edge cells. Accepted; the alternative is losing mass.
- **The revealed move is deliberately not used to collapse belief.** See ADR-009
  for the tension in the source material and why the belief chapter governs.

---

## 6. Alternatives considered

| Alternative | Why rejected |
|---|---|
| Particle filter | 49 cells make exact inference cheap; sampling would only add variance |
| Kalman filter | The state space is discrete with hard barriers; Gaussian assumptions do not hold |
| Fixed hint weight | Cannot distinguish an honest opponent from a liar — which is the entire point of the channel |
| Boost/damp re-weighting for hints | Measured to be a near-no-op after diffusion (ADR-004) |
| Trust as a hard binary (believe / ignore) | One noisy reading would flip it; the gradual estimator is robust to a ~20% false-contradiction rate |

---

## 7. Success criteria and test scenarios

| Scenario | Expectation | Test |
|---|---|---|
| Fresh map | Uniform and normalised | `test_a_fresh_belief_is_uniform_and_normalised` |
| Known start | Point mass, entropy 0 | `test_queries_report_the_posterior` |
| Scent emitted at (5,5) | (5,5) gains probability; (0,0) keeps a floor | `test_a_cell_with_no_reading_keeps_a_floor_weight` |
| Credible "north" at trust 0.9 | 0.9 of the mass moves north, 0.1 stays | `test_a_credible_claim_transports_belief_in_the_claimed_direction` |
| "North" from row 0 | Nothing moves; mass conserved | `test_mass_cannot_be_transported_through_a_wall` |
| 20 contradicted claims | Trust reaches the floor exactly | `test_trust_collapses_on_a_proven_liar` |
| 40 corroborated claims | Trust never exceeds the ceiling | `test_trust_never_reaches_certainty_even_after_a_long_honest_streak` |
| No claim, or no drift | No trust change, `hints_seen` unchanged | `test_an_unreadable_turn_is_not_scored_as_honesty` |
| Full match vs a compulsive liar | Trust collapses; every claim contradicted | `tests/integration/test_deception.py` |
| Full match vs an honest opponent | Trust stays above neutral | `test_an_honest_opponent_keeps_its_credibility` |
