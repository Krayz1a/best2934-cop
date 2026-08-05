"""What our trail looks like to the opponent: one full turn behind (I-6).

The scent field is the one channel that cannot lie -- it is emitted by the mere
act of moving and cannot be forged (book ch4). That is exactly why *when* it is
transmitted decides the whole game.

Transmitted live, the field peaks on the emitter's current cell, so sampling it
returns the opponent's position outright. Every layer built on top then becomes
decoration: the belief map has nothing left to infer, the verbal hints have
nothing left to corroborate or contradict, and the deception layer has nothing
left to hide. A cop would simply walk up the gradient.

Lagged by one full turn it becomes evidence instead of an answer. The trail
through where the opponent *was* narrows the posterior without collapsing it,
which is what makes the centroid drift worth reading (ADR-006) and what leaves a
hint something to be checked against.

The lag is a shared term, not a local choice. Two peers running different lags
would each be reading a field the other believes it is not sending, so it is
carried in the agreed config and frozen by ``config_sha256`` (rule 11).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .board import Coord

#: Full turns between emitting a field and transmitting it. Agreed with gal-roy1
#: as interop item I-6; it is their default and our reading of book ch4.
DEFAULT_TRANSMIT_LAG = 1


@dataclass
class LaggedTrail:
    """A delay line holding the scent fields we have not yet disclosed.

    Input:  a snapshot of the live field, once per turn, taken *before* the
            turn's own emission.
    Output: :meth:`transmitted`, the field the opponent is entitled to sample.
    Setup:  ``lag`` of 0 transmits live, which is legal, agreed-able and a very
            bad idea -- see the module docstring.
    """

    lag: int = DEFAULT_TRANSMIT_LAG
    history: list[dict[Coord, float]] = field(default_factory=list)

    def record(self, live: dict[Coord, float]) -> None:
        """Snapshot the field as it stands before this turn's emission.

        Copied, not referenced. ``ScentMap.grid`` is mutated in place by every
        emission and decay, so holding the same dict would produce a delay line
        whose entries all silently caught up with the present.
        """
        if self.lag <= 0:
            return
        self.history.append(dict(live))
        # Keep only what the lag can still owe. Unbounded history would grow a
        # copy of the board every turn for the whole series.
        if len(self.history) > self.lag:
            del self.history[: -self.lag]

    def transmitted(self, live: dict[Coord, float]) -> dict[Coord, float]:
        """The field the opponent may sample: ``lag`` full turns behind.

        Before the delay line has filled -- the opening turns of a sub-game --
        this is empty rather than live. Silence is the honest answer: we are
        being asked for a field from before the game started. It also cannot
        leak, which matters most in exactly the turns where the posterior is
        still wide enough for one sample to decide it.
        """
        if self.lag <= 0:
            return dict(live)
        return dict(self.history[0]) if self.history else {}
