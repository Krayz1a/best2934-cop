"""The machine-readable counted/uncounted marker (App. E rule 52).

Every artifact we write says what the match *was*; none of them said whether it
**counted**. That distinction is not cosmetic. Rule 52 hangs the league standing
on it, and the kit's own ``examples/pairing-artifacts/README.md`` asks every team
to carry a ``league`` block for exactly that reason. imreeyal does not emit one
either, which makes it a shared gap rather than a divergence -- and a gap both
teams have to close before a counted series, because two artifacts that are
silent about counted-ness are indistinguishable from two friendlies.

**Disarmed by default, and armable only by a human.** The kit is blunt about the
other direction: "a warm-up that copies them armed is a false declaration under
App. E rules 37-38". So the safe default is not "whatever the caller passed" but
*uncounted*, and arming it requires someone to have written the sign-off into
``setup.json`` -- a file no code path edits. That puts the marker downstream of
the human decision it is supposed to record, rather than beside it.

The strictest rule here is the last one: **an armed marker with no recorded
reason disarms itself.** ``counted: true`` with an empty reason is precisely the
shape a copied fixture or a hurried flag produces, and it asserts a sign-off
that nobody can point to. Refusing to arm on it costs a friendly nothing and
prevents the one mistake rules 37-38 punish.
"""

from __future__ import annotations

from typing import Any

#: Where the counted/uncounted distinction comes from. Named in the artifact so
#: a reader does not have to know which rule the boolean is answering.
AUTHORITY = "book App. E rule 52 -- declared per pairing, armed only by a human"

#: Why an unmarked pairing is uncounted. Says what to do, not merely what is.
DISARMED = (
    "no counted-game sign-off is recorded for this pairing in setup.json; "
    "this series is a friendly and must not be reported as counted"
)

#: Why an armed-but-unexplained marker is refused. See the module docstring.
UNSIGNED = (
    "counted was armed with no sign-off recorded, so it has been disarmed: "
    "an armed marker naming no agreement is a false declaration (rules 37-38)"
)


def league_block(counted: bool = False, reason: str = "") -> dict[str, Any]:
    """The ``league`` block for one pairing's result artifact.

    Input:  whether this pairing's series is counted, and the sign-off that
            says so -- both from the private, unsigned ``setup.json``.
    Output: ``{counted, authority, reason}``, the kit's shape.
    Setup:  none. Called with no arguments it produces the disarmed block,
            which is the correct answer for every friendly and every rehearsal.
    """
    recorded = reason.strip()
    if counted and not recorded:
        return {"counted": False, "authority": AUTHORITY, "reason": UNSIGNED}
    return {
        "counted": bool(counted),
        "authority": AUTHORITY,
        "reason": recorded if counted else (recorded or DISARMED),
    }
