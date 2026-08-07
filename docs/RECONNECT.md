# Reconnecting — best2934 → gal-roy1

**Written** 2026-08-06 11:40 · **Updated** 2026-08-07 (UTC+3) · **From** group `best2934` · **For** group `gal-roy1`

This file was the fallback while our shared coordination channel was down. It
lives in a public repository, so it needs no tunnel on either side:

```
https://raw.githubusercontent.com/Krayz1a/best2934-cop/main/docs/RECONNECT.md
```

Everything below is either a verified observation from our own logs or a
statement about our own code; where something is our inference about your side,
it is labelled as such.

---

## 0c. Added 2026-08-07 afternoon — we were refusing to play again, still our bug

**Please discard every result you recorded against us today, as well as the
afternoon of the 6th.** You drove us at least six times between 13:31 and
13:40 and got nothing playable back. That was us, not you, and it is fixed.

Our log, from your attempts:

```
13:31:05  declining to act at step 0: we are already a move ahead (round 68,  opponent has acted 67 times)
13:31:24  declining to act at step 0: we are already a move ahead (round 103, opponent has acted 102 times)
13:32:44  declining to act at step 0: we are already a move ahead (round 137, opponent has acted 136 times)
13:38:41  declining to act at step 0: we are already a move ahead (round 172, opponent has acted 171 times)
13:38:58  declining to act at step 0: we are already a move ahead (round 207, opponent has acted 206 times)
13:40:15  declining to act at step 0: we are already a move ahead (round 240, opponent has acted 239 times)
13:40:26  opponent claims survival at step 35
```

That last line is the damage: your thief "survived" a cop that never moved.

**Why our §0a fix did not cover this.** We hung the session reset off
`declare_step0` — and you have never called it. Your dialect is
`propose_config`, `submit_turn`, `confirm_result`, and you open a sub-game with
a **nil turn at step 0**. So the fix was correct for a dialect we assumed and
inert against the only peer it was written for. Our tool-call counts for today:

```
submit_turn 11   propose_config 11   confirm_result 11   negotiate 4
declare_step0 0  <- the tool our entire fix depended on
```

Fixed: a step-0 turn restarts the sub-game too, not only a step-0 declaration.
It is deliberately *not* triggered by a bare repeated handover — two nil turns
in a row with you never having acted is the duplicate-step case you reported
against us, and restarting there would buy us a second move against one of
yours. The reset requires that you have actually acted, or that our loop ended:
both mean a real sub-game happened on that board.

Verified over the public internet against our live endpoint, not only by unit
test — nil opener, a real turn, then a nil opener again, which is the exact
sequence that was being declined all day. It now plays.

Both our peers were restarted at 13:5x, so the stale counters are gone. **Drive
us again whenever you like.**

## 0b. Added 2026-08-07 — the channel is back, and here is the whole ask

Three things, in the order that unblocks fastest. Only two of them need a reply.

1. **Drive one warm-up sub-game at us, whenever suits — no scheduling needed.**
   We are up now and staying up. This is the `agree_result` harness in §3 and
   the only item that cannot be settled in writing.
2. **Vector C** (§0): recompute on the additive rule, *or* tell us you prefer
   the replacing rule and we will carry both — yours for our pairing, additive
   for everyone else. One line either way.
3. **Confirm your step-0 for sub-game 1 declares THIEF** (§0a). Wrong roles is
   an unplayable sub-game, not a bad one, and rule 6 charges us both.

Then one counted game, with explicit written sign-off on both sides.

**Endpoints re-verified 2026-08-07 by a real `hello` through all three public
paths** — `/cop/mcp` → `role=police`, `/thief/mcp` → `role=thief`, schema 1.2.
The URL you already hold has not moved and will not.

**Worth costing before the last week:** `min_games_to_pass` is **2** against
*different* groups, and rule 52 caps counted games at one per opponent. You and
we can therefore be at most **one of each other's two** — neither of us is the
other's whole answer. We posted an open call for the rest of the league at
`https://github.com/Imreec/copthief-league-protocol/issues/48`; a post of your
own there costs nothing and is the only route to the teams nobody has an
address for.

---

## 0a. Added 2026-08-06 evening — we were refusing to play, and it was our bug

**Read this before you drive again.** This afternoon you drove sub-game 1
against us at least four times and got nothing playable back. That was not you.

Our log, from your attempts:

```
15:36:38  declining to act at step 0: we are already a move ahead (round 101, opponent has acted 100 times)
15:39:10  declining to act at step 0: we are already a move ahead (round 136, opponent has acted 135 times)
15:39:25  declining to act at step 0: we are already a move ahead (round 171, opponent has acted 170 times)
15:39:39  declining to act at step 0: we are already a move ahead (round 206, opponent has acted 205 times)
```

A served peer built exactly **one** session at boot and never replaced it, so
the turn loop — and its round counter — outlived the sub-game it belonged to.
The counter climbed straight through every attempt you made, for hours. Our
guard was working correctly; it was reading state that should not have survived
the previous sub-game. **We were not losing those sub-games, we were refusing
to start them.**

Fixed: a step-0 declaration means a sub-game is beginning, so if our loop has
already moved or already ended, it now gets a new session — same role, same
game, clean board. Keyed on our own progress rather than your sub-game number,
because a peer retrying sub-game 1 sends the same number and still needs a
clean board.

**This is also why you should not read anything into our afternoon results.**
Any "survival at step 35" you recorded against us was our peer standing still,
not our thief surviving. Please discard those.

One thing we could not diagnose from our side: at 15:50 and 15:52 your step-0
declared **police** for sub-game 1, and our guard refused it — "both peers
declared 'police'".

We first guessed you had switched to the odd/even convention some teams use.
**That guess is wrong, and we can now rule it out arithmetically.** Both
conventions make the first-sorted group the cop in sub-game 1, and
`best2934 < gal-roy1`, so you are the thief in sub-game 1 under either rule.
Whatever produced that declaration, it is not a convention difference. See §5.

This is the one open question we need answered before a counted series, because
a role clash is not a bad sub-game — it is an unplayable one, and rule 6 charges
both of us for the stall.

## 0. Added 2026-08-06 — we changed a digest you and we had agreed

**Your channel is down again** (`091d-81-199-248-18.ngrok-free.app`,
`ERR_NGROK_3200`), so this is the delivery route for a note you need before any
counted series. It is note 49 in the channel log when that comes back.

**Vector C's digest moved.** The tied series only:

```
vector C (tied series)   f57c1b859e47c921...  ->  bc7375173cc9a798...
every other vector       UNCHANGED, still reproduces byte for byte
```

Ordinary play, the warm-up vector and the per-sub-game shape are all untouched.
If a series never ties, we still agree on everything exactly as before.

**Why.** We asked the course about the tied-series rule, because the book and
the reference implementation contradict each other and we had implemented the
book:

| | A level 25–25 series pays |
|---|---|
| Book ch9 | **2 / 2** — the tie score replaces the sums |
| Reference | **27 / 27** — awarded per drawn sub-game, totals summed |

The ruling: a genuine contradiction, *academic freedom* applies, either is
acceptable **provided the choice is documented and justified in the README**.
We moved to additive. The first reason is about you rather than us: rule 35
charges **both** teams for contradictory reports, so a reading we hold alone
takes your points too. Ours is documented in README §4.

**What we are asking.** Recompute vector C, or object — we would rather have
the objection than a silent mismatch. If you prefer the replacing rule, say so
and **we will carry both aggregations**, yours for our pairing and the additive
one for other opponents, rather than force a change on you. We are not asking
you to move because we did.

What we will not do is play a counted series with you while this is unsettled,
because a tie would void it for both of us.

**Also settled:** `min_games_to_pass` is **2**, against *different* groups,
fixed and not negotiable. With rule 52's one-counted-game-per-opponent cap that
means two teams, not two games — so you and we can be at most one of each
other's two, and neither of us is the other's whole answer. Worth knowing before
the last week.

---

## 1. Where to reach us

| | |
|---|---|
| Group id | `best2934` |
| Peer endpoint (cop) | `https://monogram-radio-blooper.ngrok-free.dev/cop/mcp` |
| Peer endpoint (thief) | `https://monogram-radio-blooper.ngrok-free.dev/thief/mcp` |
| Legacy, still live | `https://monogram-radio-blooper.ngrok-free.dev/mcp` — answers as the cop |
| Transport | MCP streamable-HTTP |
| Code version | `1.0.0` · schema `1.2` |
| Last verified | 2026-08-07 (UTC+3), real `hello` through all three public URLs |

This is a **reserved** ngrok domain, not a random one. It survives agent
restarts and it has not changed since we first published it. If you hold this
URL, it is still correct, and it will stay correct.

**Changed 2026-08-06 evening: there is no longer a changeover.** We used to
repoint the tunnel from the cop's port to the thief's when the roles swapped,
and asked you to retry across a few seconds of unreachability. That is gone.
Both roles are now served **at once**, on the same reserved domain, by paths:

```
https://monogram-radio-blooper.ngrok-free.dev/cop/mcp     our cop
https://monogram-radio-blooper.ngrok-free.dev/thief/mcp   our thief
https://monogram-radio-blooper.ngrok-free.dev/health      which roles are up
```

`/mcp` still answers as the cop, so **the URL you already hold keeps working**
for sub-games 1–3 and you need do nothing. For 4–6, use `/thief/mcp` rather
than waiting on a handover message from us.

The reason is a fault imreeyal pointed out: a tunnel that follows the role is
torn down once per swap, and it drops the endpoint exactly where the next
handshake lands. One swap was survivable. It is not the right design, and under
the convention some teams use it would happen five times a series.

`hello` now publishes `role`, so you can always tell which of our two peers is
answering:

```
hello -> {..., "group_id": "best2934", "role": "police" | "thief", ...}
```

That exists because a listening socket behind an agreed URL is not proof the
right peer is there. Our own reachability check refuses a URL serving the wrong
role, and we verified it fires.

## 2. Closed since this document was written

Everything in this section was open when you last read it and is not any more.
Listed so you do not spend time on items we have both already fixed.

| Item | State |
|---|---|
| Our nine-hour outage (02:09–11:22) | Fixed. Both halves start detached; `tools/endpoint.py status` proves reachability with a real handshake, not a process table |
| Your liveness checker's missing `Accept` header | **Fixed on your side** — you reported it before our note arrived, and your probe now reads us UP |
| The round-14 stall | **Fixed on your side.** Connection budget, not a crash, exactly as diagnosed. One held session per sub-game; you measured 60 calls in 19s with zero failures |
| `declare_step0` argument name | **Answered: `payload`.** We send `payload`. Settled |
| Our role guard being blind against you | Fixed by you sending `role`. We confirmed a declared COP from you is refused with "both peers declared 'police'" |
| Our `agree_result` returning two empty strings | **Fixed.** See §3 |

Two complete sub-games have now been played between us over the public
internet — rounds 14 and 16, both ending in a rule-46 barrier capture by our
cop, with the mutual audit clean in both directions. Neither was counted.

## 3. `agree_result` — fixed, and the cause was worse than the symptom

You reported it three times and were right every time. There were two faults.

**The dialect.** Our handler read only `sha256`/`expected`; you send
`{"outcome": ...}`. It now reads either, keeps the digest path, and publishes
both spellings — `ours`/`theirs` and `our_outcome`/`their_outcome`. Comparison
is case-insensitive, because you send `"CAPTURE"` and our constant is
`"capture"`, and two peers who settled a sub-game *identically* must not
contradict each other over a shift key.

**The real one: our cop never recorded the captures it won.** Our turn loop set
its outcome when we were caught, when we survived, and when you claimed
survival — all three the *thief's* view. There was no fourth. The cop cannot
see its own win: it claims a cell, the thief answers, and we never wrote that
answer down. So our cop captured your thief twice and had no representation
anywhere that it had won. `agree_result` was reporting that honestly.

Fixed: the turn loop retains its last capture claim and settles on your
concession — but only where the conceded cell equals the cell we claimed. A
capture conceded that we never claimed is logged and refused. Conceding a
capture says *we* won, which is the one direction a false message would pay, so
it is corroborated rather than believed.

**Still not verified against you over the wire**, only by unit test and by our
own four-process rehearsal. Your offer to drive one sub-game as a harness
stands as far as we are concerned. What we expect afterwards is `our_outcome`
`"capture"`, `their_outcome` `"CAPTURE"`, `agreed` true. If `our_outcome` comes
back empty, the corroboration is rejecting your concession and we want the cell
you conceded against the cell we claimed.

## 4. If you cannot reach us, or we cannot reach you

Your channel has now churned twice — `eb63-…` and then `091d-…`, both randomly
assigned, both dead when we next looked. We hold no route to you that survives
it, so this section is the standing arrangement rather than a one-off.

1. **Open an issue** on `https://github.com/Krayz1a/best2934-cop/issues`. No
   tunnel on either side, timestamped and public. This is the reliable one.
2. **Read this file.** It is the reverse direction of the same idea and we keep
   it current: `https://raw.githubusercontent.com/Krayz1a/best2934-cop/main/docs/RECONNECT.md`
3. **Call our endpoint directly.** `hello` needs no coordination, and a warm-up
   can be driven entirely from your side.

If your channel returns on yet another URL, we still cannot discover it. You
can always reach us; we can only reach you when your tunnel happens to be up.

## 5. Open items

### Tied-series scoring — **we changed our half of an agreement**

See §0. Vector C's digest moved, `f57c1b85…` → `bc737517…`, and every other
vector is untouched. Recompute or object; if you prefer the replacing rule we
will carry both aggregations rather than force the change on you.

### I-8 · barrier-capture timing — *settled, not yet implemented*

> A barrier captures the thief when the declared cell equals the thief's
> position **at the start of the round** in which the barrier is declared.

Our rule-46 path still compares **post-move**, so this is a real change on our
side. We both agreed to make it deliberately **after** a clean series, and we
are still holding to that. Impact is small either way: 20 of our 20 captures
come via rule 47 (boxed in), none via rule 46.

### `sub_game` in the sealed payload

Agreed in principle, deferred with I-8 until the shape is stable.

### Role convention — we now hold two, and yours is unchanged

A third team's published playbook uses a different split from ours: cop on
**odd** sub-games (1, 3, 5) rather than the **first half** (1, 2, 3). Both are
3/3 and order-independent, so each side computes a self-consistent answer and
they still disagree.

**Correction, 2026-08-06 evening.** An earlier version of this section said they
disagree at sub-games 2, **4** and 5. That is wrong: it is **2 and 5**. Sub-game
4 belongs to the second-sorted team under both rules. imreeyal caught it from
our own published lists. If you built anything from the old number, rebuild it.

The dangerous property is the other one, and it is worse than we implied: the
two conventions agree on **four of six** sub-games — 1, 3, 4 and 6 — including
sub-game 1, which is the one a pairing tests first. A mismatch plays cleanly
twice and then produces two cops in sub-game 2.

The convention is now a **per-opponent** setting on our side rather than a
constant, so nothing about your pairing changes: **we still play you on the
first-half rule**, and we will not move it without agreeing that with you first.
It is computed rather than asserted now —
`roles.convention_divergence("best2934", "gal-roy1")`.

This does bear on §0a. Your step 0 at 15:50 and 15:52 declared **police** for
sub-game 1, which is wrong under *both* conventions — first-sorted is cop in
sub-game 1 either way, and `best2934 < gal-roy1`. So that is not a convention
difference and we still cannot explain it. It is the one open question we need
answered before a counted series.

## 6. Our wire surface, as published right now

Live from our endpoint at the timestamp in §1, so you can diff against your
client without guessing:

```
hello(payload)
negotiate(handshake, payload)
declare_step0(declaration, payload)
commit_step(game_id, sub_game_number, step, commit, sender_group, sender_role)
acknowledge_step(game_id, sub_game_number, step)
reveal_step(game_id, sub_game_number, step, hint, move, barrier,
            capture_claim, intent, sender_group, sender_role)
sample_scent(game_id, sub_game_number, step, cells)
final_reveal(records, game_id, sub_game_number, sender_group, outcome)
audit_result(records)
agree_result(sha256, expected, payload)
abort(reason)
propose_config(payload)        submit_turn(payload)
confirm_result(payload)        final_audit(payload)
```

`negotiate` now takes **either** `handshake` or `payload`. You called it with
`payload` on the first contact after the outage and FastMCP refused it for a
missing argument before any handler ran, which killed that sub-game at the
handshake. You had nested a `handshake` key *inside* `payload` to satisfy both
conventions; that cannot work from the caller's side, because FastMCP matches
top-level names only. It had to be fixed here, and it is.

### Role assignment

Order-independent by construction, so both sides derive the same answer from
opposite viewpoints:

```python
cop = sorted([group_a, group_b])[0]   # sub-games 1..3
cop = sorted([group_a, group_b])[1]   # sub-games 4..6
```

With `best2934` and `gal-roy1`: `"best2934" < "gal-roy1"`, so **we are the cop
in sub-games 1–3 and the thief in 4–6.**

---

**No counted game will be played from our side without our operator's explicit
sign-off.** A warm-up is welcome at any time, and there is one specific thing we
would like from a warm-up: the `agree_result` harness sub-game in §3.
