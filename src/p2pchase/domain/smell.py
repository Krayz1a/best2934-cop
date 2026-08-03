"""Dynamic pheromone trails -- stigmergy as an indirect coordination channel.

Book chapter 4. Every agent, cop and thief alike, emits a scent field of side
``pheromone_grid_size`` (5x5) centred on the cell it occupies, with intensity
``pheromone_center_intensity`` (0.9) at the centre falling off radially. After
every FULL turn (cop and thief have both moved) the whole board decays:

    tau_ij(t+1) = max(0, (1 - rho) * tau_ij(t) + delta_tau_ij)

with rho = ``pheromone_decay`` (0.10). All three parameters are PERMANENT in
Appendix F: deviation voids the match.

The scent cannot lie. It is emitted by the mere act of moving or standing and
cannot be forged or planted -- which is precisely what makes it the yardstick
against which an opponent's *verbal* hint is measured (book ch4, "lie
detection"). Each peer reads only its OPPONENT's field.

The emission kernel itself is NOT a binding parameter -- only the centre
intensity, the decay rate and the field size are. The book therefore requires
both teams to exchange the full emission-and-decay model, including a concrete
numeric example, and lock it cryptographically before the series starts. That
is what :func:`kernel_fingerprint` is for.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field

from .board import BoardGeometry, Coord

# The literal 5x5 table printed in the book (Figure 4). This is the default so
# that any two teams reading the same figure hash to the same fingerprint.
BOOK_FIGURE_KERNEL: tuple[tuple[float, ...], ...] = (
    (0.04, 0.14, 0.20, 0.14, 0.04),
    (0.14, 0.42, 0.62, 0.42, 0.14),
    (0.20, 0.62, 0.90, 0.62, 0.20),
    (0.14, 0.42, 0.62, 0.42, 0.14),
    (0.04, 0.14, 0.20, 0.14, 0.04),
)

# A Gaussian with sigma^2 = 4/3 reproduces the book's figure to within one unit
# in the second decimal (the diagonal reads 0.43 instead of 0.42). Offered as
# an agreed alternative for teams that prefer a closed form.
GAUSSIAN_SIGMA_SQ: float = 4.0 / 3.0


def gaussian_kernel(
    size: int = 5,
    centre_intensity: float = 0.9,
    sigma_sq: float = GAUSSIAN_SIGMA_SQ,
) -> tuple[tuple[float, ...], ...]:
    """Radially symmetric emission kernel, ``centre_intensity`` at the middle."""
    if size % 2 == 0:
        raise ValueError("scent field size must be odd so it has a centre cell")
    mid = size // 2
    rows = []
    for r in range(size):
        row = []
        for c in range(size):
            d_sq = (r - mid) ** 2 + (c - mid) ** 2
            row.append(round(centre_intensity * math.exp(-d_sq / (2 * sigma_sq)), 2))
        rows.append(tuple(row))
    return tuple(rows)


def build_kernel(config: dict) -> tuple[tuple[float, ...], ...]:
    """Select the emission kernel named by the shared config."""
    ph = config.get("pheromones", {})
    size = int(ph.get("pheromone_grid_size", 5))
    centre = float(ph.get("pheromone_center_intensity", 0.9))
    mode = str(ph.get("pheromone_kernel", "book_table"))

    if mode == "book_table":
        if size != 5 or abs(centre - 0.9) > 1e-9:
            # The literal table only exists for the 5x5 / 0.9 case; anything
            # else must use the closed form so both peers can reproduce it.
            return gaussian_kernel(size, centre)
        return BOOK_FIGURE_KERNEL
    if mode == "gaussian":
        return gaussian_kernel(size, centre, float(ph.get("pheromone_sigma_sq", GAUSSIAN_SIGMA_SQ)))
    raise ValueError(f"unknown pheromone_kernel {mode!r}")


def kernel_fingerprint(kernel, decay: float) -> str:
    """SHA-256 over the emission model + a concrete worked example.

    Book ch4 requires the two teams to exchange the emission-and-decay model
    together with a numeric example, verify they read the identical formula,
    and only then lock the agreement cryptographically. This fingerprint is the
    lock: any later drift in either side's implementation shows up instantly.
    """
    centre = kernel[len(kernel) // 2][len(kernel) // 2]
    model = {
        "formula": "tau(t+1) = max(0, (1 - rho) * tau(t) + delta_tau)",
        "decay_rho": round(float(decay), 10),
        "kernel": [[round(float(v), 4) for v in row] for row in kernel],
        "worked_example": {
            "given": f"tau = {centre} at the emission centre",
            "after_one_decay_turn": round(centre * (1 - decay), 10),
        },
    }
    blob = json.dumps(model, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class ScentMap:
    """A decaying pheromone field over the board.

    One instance tracks ONE emitter. A peer keeps its own map (what it is
    leaking to the opponent) and a map of the opponent's trail as sampled from
    the protocol.
    """

    geometry: BoardGeometry
    kernel: tuple[tuple[float, ...], ...] = BOOK_FIGURE_KERNEL
    decay: float = 0.10
    grid: dict[Coord, float] = field(default_factory=dict)

    @property
    def size(self) -> int:
        return len(self.kernel)

    def emit(self, centre: Coord) -> None:
        """Deposit a fresh field around ``centre``.

        Emission is additive but capped at the centre intensity: standing still
        keeps a cell saturated rather than letting it grow without bound.
        """
        mid = self.size // 2
        peak = self.kernel[mid][mid]
        for r in range(self.size):
            for c in range(self.size):
                cell = (centre[0] + r - mid, centre[1] + c - mid)
                if not self.geometry.in_bounds(cell):
                    continue
                delta = self.kernel[r][c]
                if delta <= 0.0:
                    continue
                self.grid[cell] = min(peak, self.grid.get(cell, 0.0) + delta)

    def decay_all(self) -> None:
        """Apply one full-turn decay step to every cell."""
        factor = 1.0 - self.decay
        drained = []
        for cell, value in self.grid.items():
            new = max(0.0, value * factor)
            if new < 1e-6:
                drained.append(cell)
            else:
                self.grid[cell] = new
        for cell in drained:
            del self.grid[cell]

    def intensity(self, cell: Coord) -> float:
        return self.grid.get(cell, 0.0)

    def hottest(self) -> tuple[Coord, float] | None:
        """Cell carrying the strongest trail, or None if the board is silent."""
        if not self.grid:
            return None
        cell = max(self.grid, key=lambda k: self.grid[k])
        return cell, self.grid[cell]

    def centre_of_mass(self) -> Coord | None:
        """Intensity-weighted centroid of the trail, snapped to a cell."""
        if not self.grid:
            return None
        total = sum(self.grid.values())
        if total <= 0:
            return None
        r = sum(cell[0] * v for cell, v in self.grid.items()) / total
        c = sum(cell[1] * v for cell, v in self.grid.items()) / total
        return (int(round(r)), int(round(c)))

    def as_dict(self) -> dict[str, float]:
        """Serialisable view, keyed ``"row,col"`` so it survives JSON."""
        return {f"{r},{c}": round(v, 6) for (r, c), v in sorted(self.grid.items())}

    def load(self, payload: dict[str, float]) -> None:
        self.grid = {}
        for key, value in payload.items():
            r, c = key.split(",")
            self.grid[(int(r), int(c))] = float(value)


def build_scent_map(config: dict, geometry: BoardGeometry) -> ScentMap:
    ph = config.get("pheromones", {})
    return ScentMap(
        geometry=geometry,
        kernel=build_kernel(config),
        decay=float(ph.get("pheromone_decay", 0.10)),
    )
