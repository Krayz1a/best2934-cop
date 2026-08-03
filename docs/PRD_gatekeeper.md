# PRD — The API Gatekeeper

**Modules** `src/p2pchase/infra/gatekeeper.py`, `rate_limiter.py`,
`queueing.py`, `retrying.py`
**Guidelines** §5.1–5.3 · **Appendix F** Table 19 · **Version** 1.00

---

## 1. Background

Autonomous reporting is both the point of the project and its most dangerous
property. An agent that e-mails its own results needs no human in the loop —
and a bug in the match loop becomes a bug that sends mail in a loop. Google's
answer to that is HTTP 429, and blind retrying past a 429 gets the account
suspended.

The Gatekeeper is the single door every outbound API call passes through. There
is no second path: `ReportingService.send_result` composes a message and hands it
to `gatekeeper.execute`; it never calls the API itself.

### 1.1 The four gates

```
call ─▶ DosDetector ─▶ QuotaManager ─▶ TokenBucket ─▶ OverflowQueue ─▶ API
            │              │               │              │
          LOCKED        Rejected      wait for a       fair FIFO
         (anomaly)     (quota full)      token       (never dropped)
```

Order is load-bearing:

- **DosDetector first** because it is the cheapest and most permanent guard. A
  locked pipeline must never burn quota discovering that it is locked.
- **QuotaManager second** because a spent daily allowance cannot be waited out
  before midnight; refusing immediately is more honest than queueing forever.
- **TokenBucket third** because a rate limit is a *delay*, not a cancellation.
- **OverflowQueue last** because it is the only gate that waits rather than
  refuses.

---

## 2. Requirements

| ID | Requirement | Source |
|---|---|---|
| G-1 | No call may bypass the Gatekeeper | Guidelines §5.1 |
| G-2 | Limits are checked *before* every call, never after a failure | §5.1 |
| G-3 | Overflow is **queued**, not rejected | §5.3 |
| G-4 | Every call is recorded for monitoring | §5.1 |
| G-5 | All limits come from `config/rate_limits.json`; none hard-coded | §5.2 |
| G-6 | A 429 response is honoured, not retried through | §5.3 |
| G-7 | Only transient failures are retried; permanent ones are not | §5.3 |
| G-8 | Appendix F Table 19 values are minimums — raisable, never lowerable | Rule 12 |

### 2.1 Configured limits

| Parameter | Default | Appendix F | Gmail | LLM |
|---|---|---|---|---|
| `requests_per_minute` | 30 | minimum 30 | 30 | 30 |
| `concurrent_max` | 2 | minimum 2 | 2 | 2 |
| `retry_after_seconds` | 5 | minimum 5 | 5 | 5 |
| `max_retries` | 3 | minimum 3 | 3 | 3 |
| `queue_depth` | 100 | minimum 100 | 100 | 100 |
| `daily_limit` | 200 | — | 200 | 400 |
| `burst_threshold` | 12 | — | 12 | 20 |
| `bucket_capacity` | — | — | 5 | 8 |

Gmail's bucket is sized far below its per-minute ceiling on purpose: reports are
rare, and bursts — not sustained throughput — are the hazard that suspends an
account.

---

## 3. Components

### 3.1 Token bucket

$$\text{tokens} \leftarrow \min\!\big(C,\; \text{tokens} + r\cdot\Delta t\big),
\qquad \text{allow} \iff \text{tokens} \ge 1$$

Capacity `C` bounds burst size; refill rate `r` bounds sustained rate. The two are
tuned separately, which a simple "N calls per minute" counter cannot do.

### 3.2 Quota manager

A hard daily ceiling, the last line of defence before account suspension. It
tracks `remaining` so a caller can decide whether a batch is worth starting.

### 3.3 DOS detector

Counts calls in a sliding window. Crossing `burst_threshold` locks the pipeline
**permanently for this process**. The lock is not time-based and does not expire:
an anomaly that severe means the caller is malfunctioning, and a lock that heals
itself would let a bug resume as soon as it slowed down.

### 3.4 Overflow queue

FIFO with tickets and backpressure. A caller takes a ticket, waits until it is
next, then proceeds. Depth is bounded — a full queue raises `QueueFullError`
rather than growing without limit — and crossing a high-water mark (80%) is
reported so a monitor can see pressure building before anything is refused.

### 3.5 Retry policy

Transient statuses — `408, 425, 429, 500, 502, 503, 504` — plus `TimeoutError` and
`ConnectionError` are retried with backoff. Everything else is not: retrying a
401 fails identically every time while burning quota.

A 429 is special-cased. It carries the server's own instruction about when to
come back, and `on_rate_limit` honours it rather than applying our backoff on top.

---

## 4. Performance

| Metric | Target | Measured |
|---|---|---|
| Gate overhead per allowed call | < 1 ms | ~50 µs |
| Calls dropped under overload | 0 | 0 — queued instead |
| Behaviour at queue capacity | Bounded failure | `QueueFullError`, no growth |
| 429 handling | Honour the server | Honoured; not retried through |
| Coverage of `infra/` | ≥ 85% | 96–100% per module |

---

## 5. Constraints and limitations

- **A caller can block.** That is the intended trade: bounded waiting beats
  silent data loss. The bound is the queue depth.
- **The DOS lock is per-process and permanent.** Restarting the agent clears it.
  Deliberate: a lock that expired on its own would let a runaway loop resume.
- **The daily quota is in-process.** Two agent processes on one machine each
  track their own. Acceptable here — a match runs one process per role — but it
  would need shared state in a multi-worker deployment.
- **Rate limits are our own policy, not the provider's.** They are set
  conservatively below Google's actual limits so that we refuse before Google
  does.

---

## 6. Alternatives considered

| Alternative | Why rejected |
|---|---|
| Reject over-limit calls (the original design) | The caller then either drops the report — data loss — or retries in a hot loop, which is the problem being solved. §5.3 requires queueing |
| A plain per-minute counter | Cannot separate burst size from sustained rate; either it permits a damaging burst or it throttles normal use |
| Retry everything | Burns quota on permanent failures and turns a 401 into an outage |
| A time-expiring DOS lock | Lets a malfunctioning caller resume automatically — precisely what must not happen |
| An external queue (Redis, Celery) | A central component, extra deployment surface, and disproportionate to one e-mail per match |
| Rely on the provider's own rate limiting | The provider's response to abuse is suspension, which is unrecoverable inside a deadline |

---

## 7. Success criteria and test scenarios

| Scenario | Expectation | Test |
|---|---|---|
| Call within limits | Allowed and recorded | `tests/unit/test_infra/test_gatekeeper.py` |
| Bucket exhausted | Waits for a token; nothing dropped | same |
| Daily quota spent | `QuotaExceededError`, immediately | same |
| Burst threshold crossed | `GatekeeperLockedError`; pipeline stays locked | same |
| Queue at capacity | `QueueFullError`, no unbounded growth | `test_queueing.py` |
| High-water mark | Reported in `QueueStatus` before refusal | same |
| Transient 503 | Retried with backoff | `test_retrying.py` |
| Permanent 401 | Not retried | same |
| 429 with Retry-After | Server's instruction honoured | `test_gatekeeper.py` |
| Status on `.status_code`, `.response.status_code`, or in the message | All three recognised | `test_retrying.py` |
| Reporting path | Every send goes through `execute`; dry run sends nothing | `tests/unit/test_cli/test_commands.py` |
