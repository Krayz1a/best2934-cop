"""Figures showing the model itself: the kernel, the belief map, the entropy."""

from __future__ import annotations

import math

import matplotlib.pyplot as plt
from fig_common import GRID, deep_merge, play, save

from p2pchase import constants
from p2pchase.domain.smell import BOOK_FIGURE_KERNEL, gaussian_kernel
from p2pchase.runtime.local_match import build_side
from p2pchase.shared.config_schema import DEFAULT_SHARED


def figure_kernel() -> None:
    """The emission kernel, and where the closed form departs from the table."""
    gauss = gaussian_kernel()
    diff = [[gauss[r][c] - BOOK_FIGURE_KERNEL[r][c] for c in range(5)] for r in range(5)]

    fig, axes = plt.subplots(1, 3, figsize=(12, 3.6))
    for ax, data, title, cmap in (
        (axes[0], BOOK_FIGURE_KERNEL, "Booklet Figure 4 (table)", "inferno"),
        (axes[1], gauss, r"Gaussian, $\sigma^2 = 4/3$", "inferno"),
        (axes[2], diff, "Difference", "coolwarm"),
    ):
        im = ax.imshow(data, cmap=cmap)
        ax.set_title(title, fontsize=10)
        ax.set_xticks(range(5))
        ax.set_yticks(range(5))
        for r in range(5):
            for c in range(5):
                ax.text(c, r, f"{data[r][c]:.2f}", ha="center", va="center", fontsize=7,
                        color="white" if cmap == "inferno" else "black")
        fig.colorbar(im, ax=ax, fraction=0.046)
    fig.suptitle("Pheromone emission kernel: the two agreed forms differ on exactly "
                 "four cells, by exactly 0.01", fontsize=11)
    save(fig, "fig1_kernel.png")


def figure_belief_and_scent() -> None:
    """What the cop actually holds: a posterior and a sampled trail.

    The true thief cell is drawn as a cross for the *reader's* benefit. The cop
    never receives it -- this plot has an information advantage the agent does
    not, which is the whole point of showing them side by side.
    """
    cop, thief, _ = play()

    belief = [[cop.state.belief.probability((r, c)) for c in range(GRID)] for r in range(GRID)]
    scent = [[cop.state.opponent_scent.intensity((r, c)) for c in range(GRID)]
             for r in range(GRID)]

    fig, axes = plt.subplots(1, 2, figsize=(10, 4.4))
    for ax, data, title, cmap in (
        (axes[0], belief, r"Cop's posterior $b(s)=P(\mathrm{thief}=s \mid o_{1:t})$", "hot"),
        (axes[1], scent, r"Sampled thief trail $\tau(s)$", "viridis"),
    ):
        im = ax.imshow(data, cmap=cmap)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("column")
        ax.set_ylabel("row")
        fig.colorbar(im, ax=ax, fraction=0.046)
        tr, tc = thief.state.position
        ax.plot(tc, tr, "wx", markersize=12, markeredgewidth=2.5,
                label="true thief cell (NOT visible to the cop)")
        cr, cc = cop.state.position
        ax.plot(cc, cr, "co", markersize=9, label="cop (known to itself)")
        for br, bc in cop.state.board.barriers:
            ax.add_patch(plt.Rectangle((bc - 0.5, br - 0.5), 1, 1, fill=False,
                                       edgecolor="cyan", linewidth=1.5))
    axes[0].legend(fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.16),
                   framealpha=0.9, ncols=2)
    fig.suptitle("Local truth only (rules 8, 9): the cop holds a belief, never a position",
                 fontsize=11)
    save(fig, "fig2_belief_and_scent.png")


def figure_entropy() -> None:
    """Evidence tightens the posterior; a solo agent's only ever diffuses."""
    _, _, matched = play()

    shared = deep_merge({}, DEFAULT_SHARED)
    solo = build_side(shared, constants.ROLE_COP, "cop", {},
                      {"provider": "template", "seed": 7}, {})
    solo_curve = []
    for _ in range(len(matched)):
        solo.state.belief.predict()
        solo_curve.append(solo.state.belief.entropy())

    uniform = math.log2(GRID * GRID)
    fig, ax = plt.subplots(figsize=(7.5, 4))
    ax.plot(range(1, len(matched) + 1), matched, "o-",
            label="two-sided match (evidence arrives)")
    ax.plot(range(1, len(solo_curve) + 1), solo_curve, "s--",
            label="solo agent (diffusion only)")
    ax.axhline(uniform, color="grey", linestyle=":",
               label=f"uniform prior over 49 cells = {uniform:.2f} bits")
    ax.set_xlabel("turn")
    ax.set_ylabel("posterior entropy $H(b)$  [bits]")
    ax.set_title("Evidence is what makes the belief map worth having")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3)
    save(fig, "fig3_entropy.png")
