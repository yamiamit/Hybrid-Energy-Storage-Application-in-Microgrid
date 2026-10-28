"""
Step 5 - Particle swarm optimisation.

Searches the same design space as the grid sweep, plus the supercapacitor
string count, for the design with the lowest score (NPC when feasible).
Checked against two references:

  1. the coarse grid sweep (results/grid_sweep.csv), which PSO must match
     or beat, since it searches continuously between the grid points;
  2. a fine local grid around the PSO answer, which shows whether PSO
     landed on the true optimum at that resolution.

Several independent runs with different seeds show how repeatable the
answer is. A single lucky run proves nothing about a stochastic method.

Outputs
    results/pso_runs.csv        one row per run: best design and cost
    results/pso_history.csv     best-so-far NPC after each iteration
    figures/pso_convergence.png best NPC against simulator evaluations

Run from the project root:
    python src/pso.py
"""

import os
import time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from simulator import simulate, LPSP_TARGET, PENALTY

GRID_CSV = "results/grid_sweep.csv"
RUNS_CSV = "results/pso_runs.csv"
HISTORY_CSV = "results/pso_history.csv"
FIG = "figures/pso_convergence.png"

# =====================================================================
# CONFIG
# =====================================================================

# Search bounds. Wider than the grid on every axis, so the grid's answer
# is reachable and PSO is not boxed in by the same edges.
#            name             low     high
BOUNDS = [("pv_kw",          1000.0, 8000.0),
          ("batt_strings",      0.0,  500.0),
          ("converter_kw",    300.0, 3000.0),
          ("sc_strings",        0.0,   10.0)]

N_PARTICLES = 20
N_ITERATIONS = 40
SEEDS = [1, 2, 3, 4, 5]

# Constriction-equivalent coefficients, Clerc and Kennedy (2002):
#   w = 0.7298, c1 = c2 = 1.49618
# The standard choice that converges without hand tuning.
INERTIA = 0.7298
C_COGNITIVE = 1.49618       # pull toward the particle's own best
C_SOCIAL = 1.49618          # pull toward the swarm's best
VMAX_FRACTION = 0.20        # cap each step at 20 % of the variable's range

# Fine local grid used to check the PSO answer: half-widths and steps
REFINE = dict(pv_kw=(500, 100), batt_strings=(40, 5), converter_kw=(400, 50))

# Figure palette, shared with plot_load.py
INK = "#1C2529"
SLATE = "#4A5A62"
MUTE = "#8A979D"
ENERGY = "#C86A0A"
FLOW = "#1F7A72"
LINE = "#DCE3E5"

LO = np.array([b[1] for b in BOUNDS])
HI = np.array([b[2] for b in BOUNDS])


# =====================================================================


def evaluate(x):
    """Score one position. Integers are rounded inside simulate()."""
    pv, nb, conv, nsc = x
    npc, lpsp, score = simulate(pv, nb, nsc, converter_kw=conv)
    return score, npc, lpsp


def snap(x):
    """The design a position actually represents: integer strings, whole kW."""
    return np.round(np.asarray(x, dtype=float))


def run_pso(seed, bounds=None, n_particles=N_PARTICLES,
            n_iterations=N_ITERATIONS, record=False):
    """
    One PSO run. `bounds` overrides BOUNDS, e.g. to pin sc_strings by giving
    it equal low and high. With record=True the result also carries every
    particle's position after every iteration, for plotting the swarm.
    """
    lo = LO if bounds is None else np.array([b[1] for b in bounds])
    hi = HI if bounds is None else np.array([b[2] for b in bounds])
    best, (score, npc, lpsp), n_evals, history, trail = swarm(
        evaluate, lo, hi, seed, n_particles, n_iterations, record=record)
    res = dict(seed=seed, pv_kw=best[0], batt_strings=int(best[1]),
               batt_kwh=int(best[1]) * 60, converter_kw=best[2],
               sc_strings=int(best[3]), npc=npc, lpsp=lpsp, score=score,
               feasible=score < PENALTY, evaluations=n_evals)
    if record:
        res["trail"] = trail
    return res, history


def swarm(objective, lo, hi, seed, n_particles=N_PARTICLES,
          n_iterations=N_ITERATIONS, start=None, record=False):
    """
    The PSO search itself, for any objective that maps a snapped position to
    a tuple whose first entry is the score to minimise. `start` optionally
    places known designs as the first particles, so the swarm can only
    improve on them. Returns the best snapped position, its objective tuple,
    the number of evaluations, the convergence history and the trail.
    """
    N_PARTICLES, N_ITERATIONS = n_particles, n_iterations
    rng = np.random.default_rng(seed)
    dim = len(lo)
    vmax = VMAX_FRACTION * (hi - lo)

    pos = lo + rng.random((N_PARTICLES, dim)) * (hi - lo)
    if start is not None:
        for i, s in enumerate(start[:N_PARTICLES]):
            pos[i] = np.clip(s, lo, hi)
    trail = [pos.copy()] if record else None
    vel = rng.uniform(-vmax, vmax, size=(N_PARTICLES, dim))

    # memoise on the snapped design: rounding makes nearby positions identical
    cache = {}
    n_evals = 0

    def cost(x):
        nonlocal n_evals
        key = tuple(snap(x))
        if key not in cache:
            cache[key] = objective(key)
            n_evals += 1
        return cache[key]

    p_best = pos.copy()
    p_score = np.array([cost(x)[0] for x in pos])
    g = int(p_score.argmin())
    g_best, g_score = p_best[g].copy(), p_score[g]

    history = [dict(seed=seed, iteration=0, evaluations=n_evals,
                    best_score=g_score)]

    for it in range(1, N_ITERATIONS + 1):
        r1 = rng.random((N_PARTICLES, dim))
        r2 = rng.random((N_PARTICLES, dim))
        vel = (INERTIA * vel
               + C_COGNITIVE * r1 * (p_best - pos)
               + C_SOCIAL * r2 * (g_best - pos))
        vel = np.clip(vel, -vmax, vmax)
        pos = pos + vel

        # walls absorb: a particle that hits a bound stops there
        hit = (pos < lo) | (pos > hi)
        pos = np.clip(pos, lo, hi)
        vel[hit] = 0.0
        if record:
            trail.append(pos.copy())

        for i in range(N_PARTICLES):
            s = cost(pos[i])[0]
            if s < p_score[i]:
                p_best[i], p_score[i] = pos[i].copy(), s
                if s < g_score:
                    g_best, g_score = pos[i].copy(), s

        history.append(dict(seed=seed, iteration=it, evaluations=n_evals,
                            best_score=g_score))

    best = snap(g_best)
    return (best, cache[tuple(best)], n_evals, history,
            np.array(trail) if record else None)


def fine_grid(center):
    """Exhaustive sweep of a small box around a design, at fine steps."""
    axes = {}
    for k, (half, step) in REFINE.items():
        c = center[k]
        axes[k] = np.arange(max(0, c - half), c + half + step / 2, step)
    rows = []
    for pv in axes["pv_kw"]:
        for nb in axes["batt_strings"]:
            for conv in axes["converter_kw"]:
                npc, lpsp, score = simulate(pv, nb, center["sc_strings"],
                                            converter_kw=conv)
                rows.append(dict(pv_kw=pv, batt_strings=nb, converter_kw=conv,
                                 npc=npc, lpsp=lpsp, score=score))
    df = pd.DataFrame(rows)
    return df, axes


def figure(hist, grid_npc):
    fig, ax = plt.subplots(figsize=(8, 4.2))
    for i, (seed, h) in enumerate(hist.groupby("seed")):
        feas = h[h["best_score"] < PENALTY]
        ax.plot(feas["evaluations"], feas["best_score"] / 1e6, color=FLOW,
                lw=1.6, alpha=0.85, label="PSO, best so far (one line per seed)"
                if i == 0 else None)
    ax.axhline(grid_npc / 1e6, color=ENERGY, lw=1.6, ls="--",
               label="Grid sweep optimum (2,700 evaluations)")

    ax.set_xlabel("Simulator evaluations")
    ax.set_ylabel("Net present cost (₹ million)")
    ax.set_title("PSO convergence against the grid sweep", fontsize=11,
                 loc="left", color=INK)
    lo = hist.loc[hist["best_score"] < PENALTY, "best_score"].min() / 1e6
    ax.set_ylim(lo * 0.98, grid_npc / 1e6 * 1.12)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(LINE)
    ax.tick_params(colors=MUTE, labelsize=9)
    ax.yaxis.label.set_color(SLATE)
    ax.xaxis.label.set_color(SLATE)
    ax.grid(axis="y", color=LINE, lw=0.8, alpha=0.7)
    ax.set_axisbelow(True)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    fig.tight_layout()
    os.makedirs("figures", exist_ok=True)
    fig.savefig(FIG, dpi=150)
    plt.close(fig)
    print(f"\n  wrote {FIG}")


def main():
    if not os.path.exists(GRID_CSV):
        raise FileNotFoundError(f"{GRID_CSV} not found - run src/grid_sweep.py first")
    grid = pd.read_csv(GRID_CSV)
    grid_best = grid[grid["lpsp"] <= LPSP_TARGET].sort_values("npc").iloc[0]

    print(f"PSO: {N_PARTICLES} particles x {N_ITERATIONS} iterations,"
          f" {len(SEEDS)} independent seeds")
    runs, history = [], []
    for seed in SEEDS:
        t0 = time.time()
        res, hist = run_pso(seed)
        res["seconds"] = time.time() - t0
        runs.append(res)
        history += hist
        # evaluations needed before PSO matched the grid's answer
        hit = [h["evaluations"] for h in hist if h["best_score"] <= grid_best.npc]
        res["evals_to_match_grid"] = hit[0] if hit else None
        print(f"  seed {seed}: PV {res['pv_kw']:5.0f} kW  batt {res['batt_kwh']:6d} kWh"
              f"  conv {res['converter_kw']:5.0f} kW  SC {res['sc_strings']}"
              f"  LPSP {res['lpsp']*100:5.2f}%  NPC {res['npc']/1e6:6.1f} M"
              f"  ({res['evaluations']} evals, {res['seconds']:.0f} s)")

    runs = pd.DataFrame(runs)
    hist = pd.DataFrame(history)
    os.makedirs("results", exist_ok=True)
    runs.to_csv(RUNS_CSV, index=False)
    hist.to_csv(HISTORY_CSV, index=False)

    # --- repeatability ---
    feas = runs[runs["feasible"]]
    print(f"\n  {len(feas)} of {len(runs)} runs ended feasible")
    if feas.empty:
        print("  no feasible PSO result - increase particles or iterations")
        return
    spread = (feas.npc.max() - feas.npc.min()) / feas.npc.min() * 100
    print(f"  NPC across runs: best {feas.npc.min()/1e6:.1f} M, worst"
          f" {feas.npc.max()/1e6:.1f} M, spread {spread:.2f} %")
    print(f"  every run chose {feas.sc_strings.min()}-{feas.sc_strings.max()}"
          f" SC strings (requirement: 4)")

    # --- check 1: against the coarse grid ---
    best = feas.sort_values("npc").iloc[0]
    gain = (grid_best.npc - best.npc) / grid_best.npc * 100
    print("\n  --- against the grid sweep ---")
    print(f"  grid best   PV {grid_best.pv_kw:5.0f} kW  batt {grid_best.batt_kwh:6.0f} kWh"
          f"  conv {grid_best.converter_kw:5.0f} kW  NPC {grid_best.npc/1e6:6.1f} M"
          f"  ({len(grid)} evals)")
    print(f"  PSO best    PV {best.pv_kw:5.0f} kW  batt {best.batt_kwh:6.0f} kWh"
          f"  conv {best.converter_kw:5.0f} kW  NPC {best.npc/1e6:6.1f} M"
          f"  ({best.evaluations} evals)")
    print(f"  PSO is {gain:.2f} % cheaper" if gain >= 0 else
          f"  PSO is {-gain:.2f} % MORE expensive - it did not find the optimum")
    matched = runs["evals_to_match_grid"].dropna()
    print(f"  runs that matched the grid: {len(matched)} of {len(runs)}"
          + (f", after {matched.median():.0f} evaluations (median)"
             if len(matched) else ""))

    # --- check 2: fine local grid around the PSO answer ---
    center = dict(pv_kw=best.pv_kw, batt_strings=best.batt_strings,
                  converter_kw=best.converter_kw, sc_strings=best.sc_strings)
    fine, axes = fine_grid(center)
    fine_feas = fine[fine["lpsp"] <= LPSP_TARGET]
    fbest = fine_feas.sort_values("npc").iloc[0]
    gap = (best.npc - fbest.npc) / fbest.npc * 100
    print(f"\n  --- fine local grid around the PSO answer ({len(fine)} designs) ---")
    print(f"  steps: PV {REFINE['pv_kw'][1]} kW, battery {REFINE['batt_strings'][1]}"
          f" strings, converter {REFINE['converter_kw'][1]} kW")
    print(f"  fine best   PV {fbest.pv_kw:5.0f} kW  batt {fbest.batt_strings*60:6.0f} kWh"
          f"  conv {fbest.converter_kw:5.0f} kW  NPC {fbest.npc/1e6:6.1f} M")
    print(f"  PSO is within {gap:.2f} % of the fine-grid optimum"
          if gap >= 0 else
          f"  PSO beats the fine grid by {-gap:.2f} % (it is off the fine grid's points)")
    on_edge = [k for k in REFINE
               if fbest[k] <= axes[k][0] or fbest[k] >= axes[k][-1]]
    print("  fine-grid optimum is interior on every axis" if not on_edge else
          f"  fine-grid optimum is ON THE EDGE for {on_edge} - widen REFINE")

    full = simulate(best.pv_kw, best.batt_strings, best.sc_strings,
                    converter_kw=best.converter_kw, full=True)
    print("\n  === PSO design ===")
    print(f"  PV                 {full['pv_kw']:,.0f} kW")
    print(f"  battery            {full['n_batt_strings']} strings"
          f" = {full['e_batt_kwh']:,.0f} kWh")
    print(f"  converter          {full['converter_kw']:,.0f} kW")
    print(f"  supercapacitor     {full['n_sc_strings']} strings")
    print(f"  LPSP               {full['lpsp']*100:.3f} %")
    print(f"  NPC                {full['npc']/1e6:,.1f} M INR")
    print(f"  LCOE               {full['lcoe']:.2f} INR/kWh")
    print(f"  battery life       {full['batt_life_years']:.1f} years")

    figure(hist, grid_best.npc)


if __name__ == "__main__":
    main()
