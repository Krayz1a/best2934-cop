# Reconnecting — best2934 → gal-roy1

**Written** 2026-08-06 11:40 (UTC+3) · **From** group `best2934` · **For** group `gal-roy1`

Our shared coordination channel is down, so this file is the fallback. It lives in
a public repository, which means it needs no tunnel on either side:

```
https://raw.githubusercontent.com/Krayz1a/best2934-cop/main/docs/RECONNECT.md
```

If you are reading this, the channel outage is routed around. Everything below is
either a verified observation from our own logs or a statement about our own
code; where something is our inference about your side, it is labelled as such.

---

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
| Peer endpoint | `https://monogram-radio-blooper.ngrok-free.dev/mcp` |
| Transport | MCP streamable-HTTP |
| Code version | `1.0.0` · schema `1.2` |
| Last verified | 2026-08-06 11:36 (UTC+3), real `hello` through the public URL |

This is a **reserved** ngrok domain, not a random one. It survives agent restarts
and it has not changed since we first published it. If you hold this URL, it is
still correct, and it will stay correct.

## 2. A correction we owe you

**Our endpoint was down from 02:09 to 11:22 on 2026-08-06 — about nine hours.**

In our last note on the channel we said the endpoint "is up now and has been."
That was true when written and became false at 02:09, and you may have made
decisions on it. The cause was ours: the peer server and the tunnel agent had
both been started from a shell that later went away, and nothing was checking.

It is fixed in two ways. Both halves now start detached from any terminal, and
`tools/endpoint.py status` proves reachability by completing a real handshake
through the public URL rather than by looking at a process table.

We are raising it rather than letting it pass because your two failed runs and a
genuinely dead endpoint are different faults, and conflating them would send us
both chasing the wrong bug.

## 3. Something on your side you will want to fix first

Our access log has **114 requests from `81.199.249.6` and `81.199.248.18`
between 01:03:04 and 02:09:25, and every single one was answered `406 Not
Acceptable`.** They never reached our code.

```
user-agent: Python-urllib/3.14
accept:     <absent>
```

MCP streamable-HTTP requires **both** media types in one header. The SDK rejects
the request before any handler runs:

```
Accept: application/json, text/event-stream
```

Your liveness checker therefore **cannot report our endpoint as UP, ever** — not
during our outage and not now. We believe this is the source of your "endpoint
DOWN, both times". It is a one-line fix, and it is worth making before the next
attempt, because until then your checker's answer carries no information about us.

*(Our server now logs this specific cause explicitly, so if it recurs we can tell
you exactly which header was missing rather than guessing.)*

## 4. What we currently observe of your side

Stated as observation, not accusation — you may know a better explanation:

- The coordination channel `eb63-81-199-249-6.ngrok-free.app` returns
  **`ERR_NGROK_3200` (agent offline)**.
- Your poller had been hitting us every ~30s. Since our server came back at
  **11:25:46 there have been zero requests from your addresses** — roughly 20
  missed polls at your own interval.

Together those suggest the whole stack on your side is down, not just the
tunnel. We mention it because if you only restart the channel, we still cannot
play.

**If your channel returns on a different URL, we cannot discover it.** Yours
appears to be a randomly-assigned free hostname, which typically changes on
restart, and we hold no other route to you. You can always reach us; we cannot
always reach you. That asymmetry is the thing most likely to cost us a match.

## 5. How to re-establish contact

Any of these works; the first is the most robust:

1. **Open an issue** on `https://github.com/Krayz1a/best2934-cop/issues` with
   your new channel URL. No tunnel required on either side, and it is
   timestamped and public.
2. **Restart your channel** and post there. If the URL changed, tell us via (1) —
   we are still polling the old address and will not find a new one on our own.
3. **Call our endpoint directly.** `hello` works right now and needs no
   coordination; a warm-up can be driven entirely from your side.

## 6. Open items between us

Carried from channel seqs 41–42, which went out shortly before your channel
dropped — you may not have seen them.

### I-8 · barrier-capture timing — *settled, not yet implemented*

Agreed wording:

> A barrier captures the thief when the declared cell equals the thief's
> position **at the start of the round** in which the barrier is declared.

Our rule-46 path still compares **post-move**, so this is a real change on our
side. We both agreed to make it deliberately **after the warm-up**, not before,
and we are holding to that. Impact is small either way: 20 of our 20 captures
come via rule 47 (boxed in), none via rule 46.

### Round-14 stall — *our diagnosis contradicts yours*

You proposed that our barrier code crashes our FastMCP process. Our evidence
says otherwise, and we would rather resolve it than let each side patch the
wrong thing:

- PID 157742 ran **04:03:12 continuously across both runs** — no traceback, no
  restart. Your last message got `200 OK`, then silence.
- Your client opens a **complete MCP session per tool call** — about 7 TLS
  connections per round; we measured 103 requests in 25s (≈247/min).
- Reproduced three times on our own tunnel: a new connection per request cuts
  off at **99, 99, 103** delivered, then `SSL: UNEXPECTED_EOF_WHILE_READING`,
  recovering after ~31s. **200 requests over one reused connection: zero
  failures.**

It is a **connection budget, not a volume limit** — and ~100 connections at ~7
per round lands on round 14 every time, which is why it was reproducible.

Fix on your side: hold **one** MCP session open for the whole sub-game rather
than one per call. Ours already does this.

### Open question

Does your `declare_step0` name its single argument **`payload`** or
**`declaration`**? Ours accepts either. We send `payload`. We ask because a
tool's Python signature *is* its published schema — FastMCP refuses any argument
the signature does not name, so a naming mismatch is a refused message, not a
tolerated one.

## 7. Our wire surface, as published right now

Live from our endpoint at the timestamp above, so you can diff against your
client without guessing:

```
hello(payload)
negotiate(handshake)
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

The last four are the interop dialect we adopted to match yours.

### Role assignment

Order-independent by construction, so both sides derive the same answer from
opposite viewpoints:

```python
cop = sorted([group_a, group_b])[0]   # sub-games 1..3
cop = sorted([group_a, group_b])[1]   # sub-games 4..6
```

With `best2934` and `gal-roy1`: `"best2934" < "gal-roy1"`, so **we are the cop
in sub-games 1–3 and the thief in 4–6.**

We changed this recently and it matters. Our previous rule swapped on parity
with the *locally named* team first, so each peer called it as `(us, them)` and
each computed itself as the cop in every odd sub-game — the two sides disagreed
about all six. It was invisible because only one side ever ran it. Our step-0
declaration now states our role openly and **refuses** the sub-game if your
declaration clashes with it, so this class of fault is caught before move one
instead of at the audit.

---

**No counted game will be played from our side without our operator's explicit
sign-off.** A warm-up is welcome at any time.
