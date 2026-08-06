"""Named scent models, and the locked-model doc that pins one of them.

The book leaves the emission-and-decay model to inter-team agreement and then
freezes the signed terms as a flat key set, so a pair cannot record which model
it chose by adding a key to ``game.json`` without breaking the terms signature.
The league's answer, which several teams reached independently: publish a
document describing the choice, hash it, and declare *only the hash* in the
negotiate extras.

**The schema is the whole point.** A bare hash over an ad-hoc dict means two
teams implementing the same model from the same page still declare different
hashes -- they serialised different field sets -- and refuse each other for no
reason at all. So the doc has exactly four keys, ``family`` / ``name`` /
``params`` / ``example``, and everything model-specific lives in the last two.

Two models are registered here:

``multiplicative_book_v1``
    The book's own ch4 model, and what this codebase has always run: the
    printed figure-4 kernel as a verbatim lookup, ``tau' = clamp((1 - rho) *
    tau + delta, 0, 0.9)``, no rounding, and no receiver-side pass -- each side
    recomputes the rival's field rather than receiving it.

``subtractive_chebyshev_v1``
    The reference implementation's model: linear falloff by Chebyshev distance,
    ``tau' = round(max(0, tau - 0.1), 3)``, merged by max rather than summed,
    and the field is transmitted rather than re-derived.

Neither is the league's constant. The scent model is a **per-pair** lock -- we
run the book's model with gal-roy1 and the reference's with imreeyal -- which is
why :func:`locked_sha256` is called with an opponent's agreed name rather than
read from a global.

The examples are **derived from this module's own arithmetic**, never
transcribed. That is deliberate: it makes the published hash a test of the
physics rather than a test of our typing. An implementation that gets the
falloff or the clamp wrong cannot reach the registered digest.
"""

from __future__ import annotations

from .. import constants
from .crypto import canonical_json, sha256_hex

MULTIPLICATIVE = constants.SCENT_MULTIPLICATIVE
SUBTRACTIVE = constants.SCENT_SUBTRACTIVE
MODELS = (MULTIPLICATIVE, SUBTRACTIVE)

#: What we run against an opponent who has agreed nothing else. The book's
#: model, because the book is the one document every team in the league holds.
DEFAULT_MODEL = MULTIPLICATIVE

FAMILY = "scent_model"


def chebyshev_kernel(size: int = constants.PHEROMONE_GRID_SIZE,
                     intensity: float = constants.PHEROMONE_CENTER_INTENSITY,
                     ) -> tuple[tuple[float, ...], ...]:
    """Linear falloff by Chebyshev distance -- square rings, not radial ones.

    ``falloff = intensity / (half + 1)`` puts the outermost ring at exactly one
    step above zero rather than at zero, so a 5x5 field at 0.9 reads
    0.9 / 0.6 / 0.3 outwards and every cell of the field carries signal. A
    kernel whose rim is 0.0 would emit a 3x3 field wearing a 5x5 label.
    """
    half = int(size) // 2
    falloff = float(intensity) / (half + 1)
    return tuple(
        tuple(round(max(0.0, float(intensity) - falloff * max(abs(r - half), abs(c - half))), 3)
              for c in range(int(size)))
        for r in range(int(size)))


def subtractive_decay(value: float, decay: float = constants.PHEROMONE_DECAY) -> float:
    """One decay step under the reference model, clamped at zero.

    Rounding is part of the model rather than presentation. Without it a
    transmitted field accumulates float noise that the two peers do not share,
    and a trail compared cell by cell starts disagreeing in the tenth decimal.
    """
    return round(max(0.0, float(value) - float(decay)), 3)


def _field_at(centre: tuple[int, int], kernel, board: int) -> dict[str, float]:
    """A kernel deposited at ``centre`` and clipped to a ``board``-square grid.

    Keys are ``"r,c"`` strings because that is the shape the field takes on the
    wire, and the example has to be the thing an opponent can compare against.
    """
    half = len(kernel) // 2
    field: dict[str, float] = {}
    for r, row in enumerate(kernel):
        for c, value in enumerate(row):
            cell = (centre[0] + r - half, centre[1] + c - half)
            if 0 <= cell[0] < board and 0 <= cell[1] < board and value > 0.0:
                field[f"{cell[0]},{cell[1]}"] = value
    return field


def _subtractive_params() -> dict:
    return {
        "field_size": constants.PHEROMONE_GRID_SIZE,
        "emit_intensity": constants.PHEROMONE_CENTER_INTENSITY,
        "min_center_intensity": 0.5,
        "distance": "chebyshev",
        "falloff": "linear",
        "falloff_step": "emit_intensity / (field_size // 2 + 1)",
        "decay": "subtractive",
        "decay_per_step": constants.PHEROMONE_DECAY,
        "update": "tau' = round(max(0, tau - decay_per_step), 3)",
        "rounding_decimals": 3,
        "clamp": [0.0, None],
        "cadence": "per_full_turn",
        "order": "deposit_then_decay",
        "receiver_side_decay": True,
        "initial_field": "empty",
        "transmitted": True,
    }


def _multiplicative_params(kernel) -> dict:
    return {
        "field_size": len(kernel),
        "center_intensity": constants.PHEROMONE_CENTER_INTENSITY,
        "decay_rho": constants.PHEROMONE_DECAY,
        "kernel": [[float(v) for v in row] for row in kernel],
        "kernel_source": "book v3.0.0 figure 4 — printed values, verbatim lookup",
        "decay": "multiplicative",
        "update": "tau' = clamp((1 - rho) * tau + kernel_delta, 0, center_intensity)",
        "evaluation_order": "(1 - rho) * tau + delta, then clamp",
        "rounding_decimals": None,
        "clamp": [0.0, constants.PHEROMONE_CENTER_INTENSITY],
        "cadence": "per_full_turn",
        "order": "decay_then_deposit",
        "receiver_side_decay": False,
        "initial_field": "empty",
        "transmitted": False,
    }


def _subtractive_example(board: int = constants.GRID_SIZE) -> dict:
    """Emit at the centre of the board, then decay once. Both sides derived."""
    kernel = chebyshev_kernel()
    emitted = _field_at((board // 2, board // 2), kernel, board)
    return {
        "note": f"emit at the centre of a {board}x{board} board, then one decay",
        "emit_center": [board // 2, board // 2],
        "emit_field": emitted,
        "after_one_decay": {cell: subtractive_decay(v) for cell, v in emitted.items()},
    }


def _multiplicative_example() -> dict:
    """The clamp case, which is the one the printed formula does not cover.

    The book prints only ``max(0, ...)`` while also declaring tau to lie in
    [0, 0.9]. Without the upper bound a saturated cell that decays and is then
    deposited on again reaches 1.43, outside the book's own stated range -- so
    the clamp is required by the book even though it is not printed in the
    book, and this example is where two implementations discover whether they
    both worked that out.
    """
    tau, delta = constants.PHEROMONE_CENTER_INTENSITY, 0.62
    raw = (1 - constants.PHEROMONE_DECAY) * tau + delta
    return {
        "note": "the clamp case: a saturated cell decays, then takes an adjacent deposit",
        "tau": tau,
        "delta": delta,
        "raw": raw,
        "clamped": min(raw, constants.PHEROMONE_CENTER_INTENSITY),
    }


def locked_doc(name: str, kernel=None) -> dict:
    """The four-key document that ``<family>_sha256`` is taken over.

    ``kernel`` is only read for the book's model, whose delta table *is* the
    model; the reference's falloff is a formula and is regenerated here.
    """
    if name == SUBTRACTIVE:
        params, example = _subtractive_params(), _subtractive_example()
    elif name == MULTIPLICATIVE:
        if kernel is None:
            from .smell import BOOK_FIGURE_KERNEL

            kernel = BOOK_FIGURE_KERNEL
        params, example = _multiplicative_params(kernel), _multiplicative_example()
    else:
        raise ValueError(f"unregistered scent model {name!r}; expected one of {MODELS}")
    return {"family": FAMILY, "name": name, "params": params, "example": example}


def locked_sha256(name: str, kernel=None) -> str:
    """What we actually declare. The doc itself never crosses the wire."""
    return sha256_hex(canonical_json(locked_doc(name, kernel)))


def lock_refuses(ours: str, theirs: str) -> bool:
    """Whether two declarations are a reason not to play.

    Refusal fires **only when both peers declare and the hashes differ**.
    Omission is never refusal, in either direction, and that asymmetry is the
    part implementations get wrong: a lock that fail-fasts on a *missing*
    declaration cannot start a game against an unmodified reference peer, which
    declares nothing at all. That is a self-inflicted forfeit under rule 6, not
    a safeguard -- we would be refusing the very opponents we need.
    """
    return bool(ours) and bool(theirs) and ours != theirs
