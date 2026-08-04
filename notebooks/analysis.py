"""Analysis of the experiment data — the source for ``notebooks/analysis.ipynb``.

Kept as a plain script as well as a notebook so it can be linted, executed in
CI, and diffed in review — none of which a ``.ipynb`` does well. The notebook is
generated from this file by ``tools/build_notebook.py``; edit here, not there.

Cells are delimited by ``# %%`` markers, and a ``# %% [markdown]`` cell is prose.

    uv run python tools/build_notebook.py     # regenerate the .ipynb
    uv run python notebooks/analysis.py       # run the analysis directly
"""

# %% [markdown]
# # best2934 — experimental analysis
#
# Three questions, each answered with data rather than argument:
#
# 1. **Does the belief map earn its place?** A posterior that stays at the
#    uniform prior is decoration.
# 2. **Does lying cost the liar anything?** If not, the whole verbal layer is
#    decoration too.
# 3. **Which strategy weights does the outcome actually depend on?** Tuning a
#    parameter the result is insensitive to is wasted effort.
#
# Regenerate the inputs with:
#
# ```bash
# uv run python tools/sweep.py --seeds 60
# uv run python tools/trust_experiment.py --seeds 30
# ```

# %%
import json
import math
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
RESULTS = ROOT / "results"

UNIFORM_ENTROPY = math.log2(49)  # a flat prior over all 49 passable cells
print(f"uniform prior entropy = {UNIFORM_ENTROPY:.3f} bits")

# %% [markdown]
# ## 1 · Does the belief map earn its place?
#
# The posterior is a distribution over the 49 cells, and its Shannon entropy
#
# $$H(b) = -\sum_{s} b(s)\,\log_2 b(s)$$
#
# measures how lost the agent is. A flat prior gives $\log_2 49 = 5.61$ bits —
# maximum ignorance. Anything meaningfully below that is information the agent
# extracted from evidence.
#
# The comparison that matters is **solo versus matched**. A solo agent receives
# nothing, so its belief only diffuses; a matched agent samples the opponent's
# trail every turn.

# %%
trust = json.loads((RESULTS / "trust.json").read_text(encoding="utf-8"))
policies = trust["policies"]

entropy_curve = policies["never_lies"]["mean_entropy_curve"]
print(f"matched agent, final entropy : {entropy_curve[-1]:.3f} bits")
print(f"uniform prior                : {UNIFORM_ENTROPY:.3f} bits")
print(f"information gained           : {UNIFORM_ENTROPY - entropy_curve[-1]:.3f} bits")

# %% [markdown]
# The gap is the answer. Evidence — chiefly the unforgeable scent trail — buys
# roughly two bits, which is the difference between "somewhere on the board" and
# "in about a dozen cells".
#
# See `assets/fig3_entropy.png` for the solo-versus-matched comparison plotted
# turn by turn.

# %% [markdown]
# ## 2 · Does lying cost the liar anything?
#
# The trust coefficient is updated from a cross-examination of each claim
# against the observed drift of the opponent's scent trail:
#
# $$t \leftarrow \operatorname{clip}\big(t + \alpha (y - t),\; 0.02,\; 0.90\big),
# \qquad y = \mathbb{1}[\text{claim} = \text{observed drift}]$$
#
# with $\alpha = 0.25$. Three thief policies were run over identical boards,
# seeds and movement weights. **Only the truthfulness of the sentences differs.**

# %%
rows = []
for name in ("never_lies", "rationed", "always_lies"):
    p = policies[name]
    rows.append((name, p["final_trust_mean"], p["final_trust_stdev"],
                 p["contradiction_rate"], p["mean_lies_told"], p["capture_rate"]))

print(f"{'policy':<13}{'trust':>8}{'sd':>7}{'contradicted':>14}"
      f"{'lies/match':>12}{'captured':>10}")
for name, t, sd, cr, lies, cap in rows:
    print(f"{name:<13}{t:>8.3f}{sd:>7.3f}{cr:>13.1%}{lies:>12.1f}{cap:>10.1%}")

# %% [markdown]
# ### Reading the table
#
# **The compulsive liar destroys its own channel.** Trust reaches the 0.02 floor
# and ~97% of its claims are contradicted. Its hints stop moving the cop's belief
# at all, which is exactly what the mechanism is for.
#
# **The honest thief is believed, but not completely.** Trust settles near 0.72,
# not at the 0.90 ceiling, because ~31% of its truthful claims are still scored
# as contradictions. That is not a bug: the drift reader is roughly 80% accurate
# on turns where the opponent actually moved, and the estimator is correctly
# reflecting that its evidence is noisy. An estimator that reached the ceiling
# here would be overconfident about a measurement that genuinely is not certain.
#
# **The shipped thief sits between them.** It lies about three times per match —
# when a pursuer is close enough for misdirection to cost it a turn — and retains
# most of an honest thief's credibility. This is the design claim of
# `PRD_deception.md` §3.1, and it is what the numbers show.
#
# The residual ~31% contradiction rate against a perfectly honest opponent is
# the single largest source of error in the system, and it is documented as a
# limitation rather than tuned away.

# %%
fig, ax = plt.subplots(figsize=(7.5, 4))
for name, style in (("never_lies", "o-"), ("rationed", "s-"), ("always_lies", "^-")):
    curve = policies[name]["mean_trust_curve"]
    ax.plot(range(1, len(curve) + 1), curve, style, markersize=4, label=name)
ax.axhline(0.5, color="grey", linestyle=":")
ax.axhline(0.02, color="darkred", linestyle=":")
ax.set_xlabel("turn")
ax.set_ylabel("cop's trust in the thief")
ax.set_title(f"Trust dynamics, mean of {trust['seeds']} seeds")
ax.set_ylim(0, 1)
ax.legend()
ax.grid(alpha=0.3)
plt.show()

# %% [markdown]
# A caution about this plot: the honest curves dip between roughly turns 12 and
# 25 before recovering. Every honest run survives all 30 turns
# (`runs_alive_curve` is constant), so this is **not** an artifact of averaging
# over a shrinking sample. It is a real mid-game effect — the thief's trail
# drift becomes harder to read as it works its way into a constrained region —
# and the estimator recovers once the thief is moving freely again.

# %% [markdown]
# ## 3 · Which weights does the outcome depend on?
#
# A one-at-a-time sweep: each parameter varied alone, everything else at its
# shipped default, every level averaged over 60 independent sub-games against a
# fixed opponent. The error bar is the binomial standard error
#
# $$\mathrm{SE} = \sqrt{\frac{p(1-p)}{n}}$$
#
# which for $n = 60$ is at most 0.065. A difference smaller than about two of
# those is not a difference.

# %%
sweep = json.loads((RESULTS / "sweep.json").read_text(encoding="utf-8"))
sweep_rows = sweep["rows"]
base = next(r for r in sweep_rows if r["parameter"] == "baseline")
print(f"baseline capture rate: {base['capture_rate']:.3f} "
      f"± {base['capture_stderr']:.3f}   ({base['matches']} matches)")

params = [p for p in dict.fromkeys(r["parameter"] for r in sweep_rows) if p != "baseline"]

# %%
print(f"{'parameter':<24}{'range of capture rate':>22}{'sensitive?':>13}")
sensitivity = []
for name in params:
    pts = [r for r in sweep_rows if r["parameter"] == name]
    lo = min(p["capture_rate"] for p in pts)
    hi = max(p["capture_rate"] for p in pts)
    spread = hi - lo
    # Two standard errors of the widest cell: below this, the spread is noise.
    threshold = 2 * max(p["capture_stderr"] for p in pts)
    sensitive = spread > threshold
    sensitivity.append((name, pts[0]["role"], lo, hi, spread, sensitive))
    print(f"{name:<24}{lo:>10.3f} – {hi:<8.3f}{'YES' if sensitive else 'no':>10}")

# %%
sensitivity.sort(key=lambda row: row[4], reverse=True)
fig, ax = plt.subplots(figsize=(7.5, 4))
ax.barh([f"{r[1]}: {r[0]}" for r in sensitivity], [r[4] for r in sensitivity],
        color=["tab:red" if r[5] else "tab:grey" for r in sensitivity])
ax.set_xlabel("spread in capture rate across the swept levels")
ax.set_title("Sensitivity ranking (grey = within noise)")
ax.grid(alpha=0.3, axis="x")
plt.show()

# %% [markdown]
# ### What this says about tuning
#
# The parameters at the top of the ranking are where tuning effort belongs. The
# grey ones are within noise at 60 matches per level — for those, the shipped
# default sits on a plateau and moving it buys nothing measurable.
#
# One result is worth calling out on its own: setting the thief's
# `distance_weight` to zero makes it *always* get caught. A thief that ignores
# distance entirely optimises purely for open space and walks straight into the
# cop. This is the sanity check that the sweep is measuring something real —
# a parameter that should matter enormously does.
#
# ## 4 · Token cost
#
# Every measurement above was produced with the `template` talk provider, which
# costs **zero tokens**. The whole experimental programme — several thousand
# sub-games — cost nothing, and a full league series costs nothing.
#
# | Provider | Tokens / series (6 sub-games, ~210 hints) | Notes |
# |---|---|---|
# | `template` | **0** | Default. Offline, no account, cannot fail |
# | `ollama` | 0 billed | Local compute; reported as 0 against the agreed budget |
# | `claude_api` | ~13k–17k | Measured from `usage`; small model, one short sentence per hint |
# | `claude_cli` | ~25k estimated | The CLI reports no usage, so this is declared as an estimate |
#
# Against the agreed budget of 200,000 tokens per series, even the most
# expensive mode uses well under a fifth. The point of the default, though, is
# not thrift: with `template` the competition reduces to the quality of the
# movement algorithm, which is where the booklet says the grade lives.

# %%
tokens = sum(r["tokens"] for r in sweep_rows)
print(f"total tokens consumed across the entire sweep: {tokens}")
assert tokens == 0, "the sweep is supposed to be free"

# %% [markdown]
# ## 5 · Integrity, as a by-product
#
# Every sub-game in every experiment above wrote a commit chain, and every one
# of them was verified. This is not a separate experiment — it is a property
# asserted on every match the project has ever played.

# %%
verified = all(r["all_logs_verified"] for r in sweep_rows)
matches = sum(r["matches"] for r in sweep_rows)
print(f"{matches} sub-games played; every commit chain verified: {verified}")
assert verified
