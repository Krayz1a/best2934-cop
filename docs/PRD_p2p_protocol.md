# PRD — The Peer-to-Peer Protocol over MCP

**Modules** `src/p2pchase/mcp/`, `src/p2pchase/runtime/peer.py`,
`peer_session.py`, `watchdog.py`
**Booklet** ch2, ch5.3.2, ch8 · **Rules** 1, 2, 4, 5, 6, 10, 11 · **Version** 1.00

---

## 1. Background

Rule 1 requires the cop and the thief to run in two fully separate processes.
Rule 2 forbids shared memory between them. Rule 10 puts a league match across the
public internet through a tunnel. Together these rule out every shortcut: there
is no shared engine, no common referee, and no in-process handoff.

The protocol is **symmetric**. Each agent runs a FastMCP server *and* a client,
and both peers execute the identical loop. There is no initiator and no
responder, because an asymmetric protocol would need one side to be trusted with
sequencing — and there is nobody to trust.

### 1.1 One step, from one peer's side

```
prepare → push COMMIT → await their COMMIT → push REVEAL
        → await their REVEAL → sample their scent → apply
```

Both peers do this concurrently. The order — commit before either reveals — is
what makes the commitment meaningful (see [PRD_commit_reveal.md](PRD_commit_reveal.md)).

---

## 2. Requirements

| ID | Requirement |
|---|---|
| P-1 | Two processes; a real socket even when both peers sit on one laptop |
| P-2 | Symmetric protocol: no initiator, no responder |
| P-3 | Eleven tools, exactly the set declared in the contract — no more, no less |
| P-4 | A refusal is data (`{"ok": false, "reason"}`), never an exception across the wire |
| P-5 | Every wait is bounded by two independent clocks |
| P-6 | An out-of-order message is rejected, not tolerated |
| P-7 | Fingerprints are exchanged and compared before move one (rule 11) |
| P-8 | An abort is delivered best-effort, then the peer stops regardless |
| P-9 | Result-shape differences across FastMCP versions must not lose a match |
| P-10 | A move is applied only after the opponent has acknowledged |

---

## 3. The tool contract

| Tool | Payload | Response |
|---|---|---|
| `hello` | — | `{ok, handshake, tools}` |
| `negotiate` | `{handshake}` | `{ok, agreed, mismatches}` |
| `declare_step0` | signed declaration | `{ok}` |
| `commit_step` | `{game_id, sub_game_number, step, commit}` | `{ok}` |
| `acknowledge_step` | `{game_id, sub_game_number, step}` | `{ok, held}` |
| `reveal_step` | `{…, move, hint, barrier?, capture_claim?}` | `{ok, caught}` |
| `sample_scent` | `{…, cells: [[r,c], …]}` | `{ok, samples: {"r,c": τ}}` |
| `final_reveal` | `{records}` | `{ok, records}` |
| `audit_result` | `{records}` | `{ok, passed, failed_steps}` |
| `agree_result` | `{sha256, expected}` | `{ok, agreed}` |
| `abort` | `{reason}` | `{ok}` |

The set is asserted in both directions: every contract tool must be registered,
and no tool may be exposed that the contract does not name. Undeclared surface is
surface nobody agreed to.

### 3.1 How a capture ends a sub-game (rules 21, 22, 46, 47)

Nobody can see the opponent, so nobody can *observe* a capture. It is claimed
and answered instead, inside the reveal both peers were already exchanging:

```
cop  → reveal_step(move, hint, capture_claim = the cell I am moving onto)
thief→ {ok, caught: true|false}          # answered from its own true cell
```

The cop names the only cell it can speak for honestly -- its own -- and the
thief is the only party able to check it. A barrier sealed on the thief's cell
is claimed the same way (rule 46), and a thief left with no legal move ends the
sub-game from its own side (rule 47), because only the thief can see that.

Both the claim and the answer are inside the commit chain, so a false denial is
provable at the final audit and forfeits the game (rule 22). The mechanism is
honest because lying is strictly worse, not because either side is trusted.

The cost is that the thief learns the cop's cell every turn. That asymmetry is
deliberate: the pursued may see the pursuer, and without a claim rules 21 and 22
would have nothing to govern.

### 3.2 Why handlers are MCP-free

`PeerHandlers` is a plain object mapping dict → dict, with no MCP import. The
FastMCP binding in `mcp/server.py` is a thin adapter containing no logic of its
own, and a test asserts that a tool invoked through the server returns exactly
what the handler returns directly.

This is what makes the protocol testable. A complete COMMIT/ACK/REVEAL exchange
between two handler objects runs in microseconds with no sockets and no ports, so
the interesting failure cases — a reveal with no commitment, a message for the
wrong game, a step out of order — get tested properly instead of being left to a
live match against a stranger.

---

## 4. The two clocks

| Clock | Timeout | Measures | Fed by |
|---|---|---|---|
| `TurnDeadline` | 30 s | Time since this message was sent | Reset per await |
| `Watchdog` | 60 s | Time since the last *completed step* | `beat()` only |

The distinction matters. A single per-message timeout cannot catch an opponent
that answers every message promptly while never advancing the game — a livelock
in which both peers are technically responsive and nothing happens. The watchdog
measures progress, so it trips.

Rule 6 makes an unfinished sub-game a technical loss for **both** teams, which
means aborting cleanly is strictly better than waiting politely.

### 4.1 Waiting on state, not on time

`_await_reveal` waits on `opponent_steps_seen >= step`, not on a sleep. A peer
therefore never advances past an opponent whose message is merely slow — it
advances when the message actually arrives, or it trips a clock.

---

## 5. Negotiation (rule 11)

Before move one, peers exchange:

| Fingerprint | Purpose |
|---|---|
| `group_id` | Rule 3 — a unique 8-character code per team. Identical ids are refused |
| `config_sha256` | The agreed physics must be byte-identical |
| `scent_fingerprint` | SHA-256 over the emission model, decay and a worked example |
| `code_version` | Compatibility of the protocol implementation |

A single mismatch refuses the match with the specific difference named. Playing
a match that rule 11 already voids is pure waste, so the refusal happens at the
handshake rather than at the audit.

---

## 6. Performance

| Metric | Target | Measured |
|---|---|---|
| Local decision per turn | ≪ 30 s deadline | ~1 ms |
| Loopback sub-game, 8 steps, both peers concurrent | — | ~2.5 s (dominated by poll interval) |
| Poll interval while awaiting | Responsive without spinning | 50 ms |
| Deadlock under concurrent play | 0 | 0 — exercised with `asyncio.gather` |
| Message shapes tolerated | 4 | structured content, `.data`, `.content`, plain dict |

---

## 7. Constraints and limitations

- **Polling, not events.** `_await_condition` polls every 50 ms rather than
  waiting on a condition variable. Simpler and adequate for a 35-step game; it
  would not scale to thousands of concurrent matches.
- **The loopback client is for tests only.** Using it for a real match would
  violate rules 1 and 2, and it is documented as such at its definition.
- **No transport-level authentication.** An attacker who reaches the endpoint can
  send protocol messages. Mitigated by commit-reveal — they cannot forge a
  consistent chain — and by the tunnel URL not being published. Out of scope for
  a course league.
- **Tunnels are the operator's job.** The server binds `127.0.0.1` by default;
  exposing the port is explicitly the tunnel's responsibility, so nothing is
  published to the internet by accident during development.

---

## 8. Alternatives considered

| Alternative | Why rejected |
|---|---|
| One agent hosts, the other connects | The host sequences the game and is a de-facto referee |
| A message broker between peers | A central component by another name |
| Raw HTTP/JSON instead of MCP | The course specifies MCP; and MCP gives tool schemas and discovery for free |
| WebSockets | Adds connection-state management for no gain over request/response at this turn rate |
| Raising exceptions across the wire | The opponent cannot distinguish a refusal from a crash, and rule 6 charges both teams for a stall |
| Pinning one FastMCP version | Losing a league match to a library upgrade on the opponent's side would be absurd; all result shapes are accepted instead |

---

## 9. Success criteria and test scenarios

| Scenario | Expectation | Test |
|---|---|---|
| All eleven tools registered | Contract set exposed exactly | `tests/unit/test_mcp/test_server_binding.py` |
| Tool via server vs handler direct | Identical answers | same |
| FastMCP absent | A sentence, not an ImportError traceback | same |
| `serve()` binding | Loopback host, configured port | same |
| Eight-step sub-game, both peers concurrent | Completes, no deadlock | `tests/integration/test_networked_sub_game.py` |
| Every reveal seen | `opponent_steps_seen == 8`, commitments 1–8 | same |
| Mutual audit | Each peer verifies the other | same |
| Tampered record | Fails at the correct step | same |
| Belief crossed the wire | Entropy below the uniform prior; scent sampled | same |
| Reveal without a commitment | Refused | same |
| Unknown tool | Refusal, not a dropped call | `tests/unit/test_mcp/test_client.py` |
| Mismatched fingerprints | Refused with the mismatch named | same |
| Transport failure | Names the tool that failed | same |
| Missing opponent URL | Refuses to guess an endpoint | `tests/unit/test_cli/test_network_commands.py` |
| Failed handshake | Aborts before move one | same |
