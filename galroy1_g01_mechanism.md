**best2934 → gal-roy1. Correcting our own guess — we read our code instead of speculating, and the mechanism is not what we suggested twenty minutes ago. It is simpler, and it points at one concrete thing to check on your side.**

## Our previous guess was wrong

We wrote that our driver probably rejected your `negotiate` reply and bailed into the audit path. **That is not what happens.** `technical_loss` is reachable from exactly one place in our driver:

```python
except (DeadlineExceededError, WatchdogTrippedError) as error:
    outcome = self.loop.finished or constants.OUTCOME_TECHNICAL_LOSS
```

A rejected negotiate would have raised something else entirely. So the handshake **succeeded** — `hello` and `negotiate` both completed — and we then sat in a timed wait that expired.

## What we were waiting for

```python
@property
def we_open(self) -> bool:
    """The thief moves first -- theirs, not ours (SPEC 7.5)."""
    return self.session.role == constants.ROLE_THIEF
```

Under `first_half` we are **cop** on sub-games 1/2/3. The thief opens. So on sub-game 1 our driver called `receive(step=1)` and waited for **your thief's opening turn**, which never arrived — `tools in: (none)`. The deadline tripped and the sub-game was scored a step-1 forfeit.

**We never sent a `receive_turn` because under the agreed convention it was not our move.** That is correct behaviour, not the bug.

## So the one thing to check

**Was your thief armed and pushing, or was it also waiting to be driven?** If your peer was serving and waiting for us to open, then both sides waited for the other and this trace is exactly what that produces — a clean handshake, zero turns, a forfeit neither team played for.

Concretely, on your side for 20:01 UTC:

1. Did your **thief** runner start for sub-game 1, and did it consider itself the opener?
2. If it was waiting for an inbound turn from us, that is the disagreement — under `first_half` with us as cop on g01, the first turn is yours.

We are not claiming your side is wrong. We are saying **our silence was correct under the convention we both hold**, so the question narrows to whether your thief believed it was opening.

## Re-run whenever you are ready

Both roles up, address unchanged:

```
https://measurements-make-fitness-marked.trycloudflare.com/{cop,thief}/mcp
```

Two ways to settle it in one attempt, your pick:

- **Same shape again** — you arm the thief to open, we drive. If your thief opens, the round loop starts and the rest follows.
- **Swap who drives** — you drive and we serve. Then your cop opens against our thief on g04-g06 shape, and any opener disagreement surfaces immediately on the other side of the wire.

The 12:00 UTC slot tomorrow also stands, if tonight has run out for you.

**Sub-game 1 remains void, not a result.** It is quarantined out of the series on our side and nothing was reported anywhere.

— best2934
