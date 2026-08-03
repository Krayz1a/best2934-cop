# PRD — Commit-Reveal Integrity and Mutual Audit

**Modules** `src/p2pchase/domain/crypto.py`, `src/p2pchase/ui/replay.py`,
`src/p2pchase/services/verification_service.py`
**Booklet** ch5.3, ch7.4–7.5 · **Rules** 17–20, 24, 36 · **Version** 1.00

---

## 1. Background

A two-player game with no referee has a structural temptation: whichever agent
moves second can choose its move after seeing the first. Nothing in a
peer-to-peer protocol prevents this by construction, because there is nobody to
appeal to.

Commit-Reveal removes the temptation cryptographically. Before either agent
learns anything about the other's turn, each publishes

$$H = \text{SHA-256}\big(\text{canonical\_json}(payload) \;\|\; \text{nonce}\big)$$

The hash is *binding* — finding a second payload with the same digest is
computationally infeasible — and *hiding*: the 128-bit nonce means the digest
reveals nothing about the move it seals.

This carries the spirit of a zero-knowledge proof (booklet §5.3): during play,
each agent proves it has decided without disclosing what it decided.

### 1.1 Protocol per step

```
COMMIT  →  ACK  →  REVEAL  →  APPLY
```

and once per sub-game, at the end:

```
FINAL_REVEAL  →  AUDIT  →  AGREE
```

Rule 18 places the nonce disclosure at `FINAL_REVEAL` only. Until then a peer has
published its hash and its payload, but nothing that lets the opponent
recompute — and therefore nothing exploitable mid-match.

---

## 2. Requirements

| ID | Requirement |
|---|---|
| C-1 | Every step is committed before the opponent acts |
| C-2 | Payloads are serialised canonically, so two machines hash identically |
| C-3 | Nonces are ≥128 bits, cryptographically random, unique per step |
| C-4 | Nonces are withheld until the end of the sub-game (rule 18) |
| C-5 | Each commitment binds a `state_digest` of the board it was made on |
| C-6 | The Step-0 hardware declaration is **committed**, not written raw |
| C-7 | Audit re-derives every hash and names each failing step |
| C-8 | A reveal with no prior commitment is refused |
| C-9 | An integrity failure is a technical loss scoring 0, never a warning (rule 19) |

### 2.1 Input / output

| Operation | Input | Output |
|---|---|---|
| `commit(payload)` | Step payload dict | `CommitRecord(payload, nonce, commit)` |
| `revealed_view()` | — | `{payload, commit}` — nonce withheld |
| `audit_view()` | — | `{payload, nonce, commit}` — full disclosure |
| `audit_records(records)` | Disclosed chain | `{passed, verified_steps, failed_steps}` |
| `sign_declaration(payload, secret)` | Step-0 payload | HMAC-style SHA-256 signature |
| `mutual_agreement_hash(summary)` | Result summary | Digest both teams compare (rule 35) |

---

## 3. Design notes

### 3.1 Why `state_digest` is in the payload

Without it, a commitment is a statement about a move in the abstract. With it,
the commitment is bound to the exact board — position, barriers, step number — on
which it was made. An old commitment therefore cannot be replayed in a new
context (booklet §5.3.1).

### 3.2 Why Step 0 is committed and not just signed

Rule 24 requires a signed hardware declaration before play, so a team cannot
retroactively claim weaker hardware and farm the computational-fairness bonus.

But a signature we compute ourselves can be *re*computed at any time. Signing
proves we declared it; **committing** proves we declared it *before the match and
never edited it afterwards*, because the commitment sits at position 0 of a chain
whose later entries are all bound to steps that have since been played.

> This was a real bug. Step 0 was originally written raw into the log, so every
> log failed replay at step 0 with `INTEGRITY FAILURE — tampering proven at
> step(s) 0`. Wrapping it in `commit(payload).audit_view()` fixed it, and the
> resulting property is stronger than the one rule 24 asks for.

### 3.3 Why canonical JSON

Two peers must hash identically. Python's default `json.dumps` varies with key
insertion order and whitespace, so `canonical_json` sorts keys, fixes separators
and disables ASCII escaping. Any drift here would make honest peers accuse each
other of cheating.

### 3.4 Refusals over exceptions

`reveal_step` for a step with no recorded commitment raises locally but is
returned to the opponent as `{"ok": false, "reason": …}`. An exception crossing
MCP arrives as an opaque transport failure the opponent cannot tell apart from a
crash, and rule 6 charges *both* teams for a stalled sub-game.

---

## 4. Performance

| Metric | Target | Measured |
|---|---|---|
| Commit cost per step | < 1 ms | ~20 µs |
| Full 36-record audit | < 50 ms | ~3 ms |
| Tampered-log detection | 100% | 100% — asserted, not assumed |
| False-positive rate on intact logs | 0% | 0% across every generated log |

---

## 5. Constraints and limitations

- **Verification is deferred.** Nonces arrive only at the end, so a cheating peer
  is caught after the sub-game rather than during it. Accepted: the penalty is a
  technical loss either way, and rule 18 requires this ordering.
- **The commitment binds a move, not a promise to be a good sport.** It proves
  the move was chosen before the opponent's was known. It says nothing about
  whether the *hint* was true — that is deliberately a separate mechanism (see
  [PRD_deception.md](PRD_deception.md)).
- **The signing secret is not shared.** It authenticates the declaration to
  ourselves and to a grader who is given the secret; it is not a public-key
  signature an arbitrary third party can verify.

---

## 6. Alternatives considered

| Alternative | Why rejected |
|---|---|
| Digital signatures (Ed25519) instead of hashes | Authenticate the *author*, not the *timing*. The property at issue is "decided before seeing yours", which a signature does not provide |
| Reveal the nonce each step | Rule 18 forbids it, and it buys nothing — the payload is already disclosed |
| A blockchain / append-only ledger | A central component by another name, and vastly disproportionate to 36 records |
| Trusting the opponent's self-reported audit | The exact failure mode the mechanism exists to remove |
| MD5 or SHA-1 | Broken collision resistance; the binding property would not hold |

---

## 7. Success criteria and test scenarios

| Scenario | Expectation | Test |
|---|---|---|
| Intact chain | `Verified OK — N/N steps` | `tests/unit/test_domain/test_crypto.py` |
| One altered move | Fails, naming exactly that step | `test_a_tampered_log_fails_the_opponents_audit` |
| Altered nonce | Fails at that step | `tests/unit/test_domain/test_crypto.py` |
| Same payload committed twice | Different nonces, different digests | same |
| Reveal without a commitment | Refused with a clear reason | `test_a_reveal_without_a_prior_commitment_is_refused` |
| Step 0 in a written log | Carries a commitment; signature present | `test_step_zero_is_committed_and_verifies_with_the_rest` |
| Edited hardware declaration | Signature no longer matches | `tests/unit/test_infra/test_sysinfo.py` |
| Full networked sub-game | Both chains verify; each peer audits the other | `tests/integration/test_networked_sub_game.py` |
| Result digests | Match for identical summaries; a wrong digest is rejected | `test_both_teams_computing_the_same_result_agree` |
