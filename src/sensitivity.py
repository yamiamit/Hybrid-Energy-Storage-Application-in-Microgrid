"""
Step 11 - Sensitivity analysis.

tornado.png (plot_results.py) moves one input at a time by a fixed amount.
This script goes further:

  spider        re-optimised NPC as each input moves step by step, so the
                slope and any bend show, not just two end points
  two-way       PV price and battery price moved together; the NPC and the
                design the optimiser picks for each pair
  reliability   the LPSP target itself: what each step of reliability costs
                and how the design changes to deliver it
  Monte Carlo   every uncertain input at once, including the weather year,
                on the fixed optimum design: the spread of NPC, the chance
                of missing the 1 % LPSP target, and which inputs drive each

Every point in the first three re-runs PSO, so each shows the cost of the
best design under those conditions, not of today's design. Results are
cached in results/; delete a CSV to recompute it.

Outputs
    results/sens_spider.csv       figures/sens_spider.png
    results/sens_twoway.csv       figures/sens_twoway.png
    results/sens_reliability.csv  figures/sens_reliability.png
    results/montecarlo.csv        figures/sens_montecarlo.png

Run from the project root, after pso.py and performance.py:
    python src/sensitivity.py
"""

import contextlib
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import spearmanr

import simulator
import pso
import performance
from simulator import simulate, load_inputs, PENALTY, BATT_KWH_PER_STRING
from costs import PV, BATTERY_LA, CONVERTER, ECON
from plot_load import style, INK, SLATE, MUTE, ENERGY, FLOW

OUT = "figures"
SPIDER_CSV = "results/sens_spider.csv"
TWOWAY_CSV = "results/sens_twoway.csv"
RELIABILITY_CSV = "results/sens_reliability.csv"
MC_CSV = "results/montecarlo.csv"

# =====================================================================
# CONFIG
# =====================================================================

STEPS = [-0.2, -0.1, 0.0, 0.1, 0.2]          # fractional change, spider plot
DERATING_STEPS = [-0.06, -0.03, 0.0, 0.03, 0.06]   # derating cannot pass 1
TWOWAY = [0.6, 0.8, 1.0, 1.2, 1.4]            # PV and battery price factors
LPSP_TARGETS = [0.001, 0.0025, 0.005, 0.01, 0.02, 0.03, 0.05, 0.10]
REOPT = dict(n_particles=20, n_iterations=30)
SEED = 1

MC_SAMPLES = 1000
MC_SEED = 7
# Monte Carlo inputs: uniform within +/- these fractions of the base value
MC_RANGES = {"PV price": 0.20, "Battery price": 0.20, "Converter price": 0.20,
             "Real discount rate": 0.20, "Battery cycle life": 0.20,
             "PV derating": 0.06, "Annual demand": 0.10}

BATT = "#2a78d6"
UNMET = "#e34948"
SEQ = plt.matplotlib.colors.LinearSegmentedColormap.from_list(
    "blue", ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])

# Colour follows the equipment (PV teal, battery blue, demand amber);
# line style tells a price (solid) from a technical input (dashed).
LOOK = {"PV price": (FLOW, "-"), "Battery price": (BATT, "-"),
        "Converter price": (MUTE, "-"), "Real discount rate": (INK, "-"),
        "Annual demand": (ENERGY, "-"), "Battery cycle life": (BATT, "--"),
        "PV derating": (FLOW, "--")}

# =====================================================================


@contextlib.contextmanager
def changed(name, f):
    """Temporarily multiply one input by f (the simulator reads them live)."""
    keys = {"PV price": [(PV, "capital_inr_per_kw"), (PV, "replacement_inr_per_kw")],
            "Battery price": [(BATTERY_LA, "capital_inr_per_unit"),
                              (BATTERY_LA, "replacement_inr_per_unit")],
            "Converter price": [(CONVERTER, "capital_inr_per_kw"),
                                (CONVERTER, "replacement_inr_per_kw")],
            "Real discount rate": [(ECON, "real_discount")],
            "PV derating": [(PV, "derating")]}
    if name in keys:
        saved = [(c, k, c[k]) for c, k in keys[name]]
        for c, k, v in saved:
            c[k] = v * f
        try:
            yield
        finally:
            for c, k, v in saved:
                c[k] = v
    elif name == "Battery cycle life":
        saved = simulator.BATT_CYCLE_LIFE
        simulator.BATT_CYCLE_LIFE = tuple((d, n * f) for d, n in saved)
        try:
            yield
        finally:
            simulator.BATT_CYCLE_LIFE = saved
    elif name == "Annual demand":
        d = load_inputs()
        saved = d["load"]
        d["load"] = saved * f
        try:
            yield
        finally:
            d["load"] = saved
    else:
        raise KeyError(name)


def reoptimise(start, lo=None, hi=None):
    """Best design under the current inputs, warm-started from `start`."""
    lo = pso.LO if lo is None else lo
    hi = pso.HI if hi is None else hi
    best, (score, npc, lpsp), _, _, _ = pso.swarm(pso.evaluate, lo, hi, SEED,
                                                  start=[np.array(start)], **REOPT)
    ok = score < PENALTY
    return dict(npc=npc if ok else np.nan, lpsp=lpsp, pv_kw=best[0],
                batt_strings=int(best[1]), converter_kw=best[2], feasible=ok)


def cached(path, build):
    if os.path.exists(path):
        print(f"  (reusing {path} - delete it to recompute)")
        return pd.read_csv(path)
    df = build()
    df.to_csv(path, index=False)
    return df


# ---------------------------------------------------------------------
# Studies
# ---------------------------------------------------------------------

def spider(start):
    rows = []
    for name in LOOK:
        steps = DERATING_STEPS if name == "PV derating" else STEPS
        for s in steps:
            with changed(name, 1.0 + s):
                r = reoptimise(start)
            rows.append(dict(parameter=name, change=s, **r))
            print(f"    {name:20s} {s:+.0%}  NPC ₹{r['npc']/1e6:6.1f} M")
    return pd.DataFrame(rows)


def twoway(start):
    rows = []
    for fp in TWOWAY:
        for fb in TWOWAY:
            with changed("PV price", fp), changed("Battery price", fb):
                r = reoptimise(start)
            rows.append(dict(pv_factor=fp, batt_factor=fb, **r))
            print(f"    PV ×{fp:.1f}  battery ×{fb:.1f}  NPC ₹{r['npc']/1e6:6.1f} M")
    return pd.DataFrame(rows)


def reliability(start):
    rows = []
    hi = pso.HI.copy()
    hi[0], hi[1] = 12000.0, 900.0              # room for very reliable designs
    saved = simulator.LPSP_TARGET
    try:
        for t in LPSP_TARGETS:
            simulator.LPSP_TARGET = t
            r = reoptimise(start, hi=hi)
            rows.append(dict(target=t, **r))
            print(f"    LPSP ≤ {t:.2%}  NPC ₹{r['npc']/1e6:6.1f} M")
    finally:
        simulator.LPSP_TARGET = saved
    return pd.DataFrame(rows)


def montecarlo(design):
    pv, nb, conv, sc = design
    rng = np.random.default_rng(MC_SEED)
    rows = []
    for i in range(MC_SAMPLES):
        draw = {k: 1.0 + rng.uniform(-w, w) for k, w in MC_RANGES.items()}
        year = int(rng.choice(performance.YEARS))
        with contextlib.ExitStack() as stack:
            stack.enter_context(performance.use_weather(year))
            for k, f in draw.items():
                stack.enter_context(changed(k, f))
            npc, lpsp, _ = simulate(pv, nb, sc, converter_kw=conv)
        ghi = performance.weather(year)[0].sum() / 1000
        rows.append(dict(sample=i, year=year, sunshine=ghi, npc=npc, lpsp=lpsp,
                         **{k: v for k, v in draw.items()}))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------

def save(fig, name):
    fig.tight_layout()
    fig.savefig(f"{OUT}/{name}", dpi=150)
    plt.close(fig)
    print(f"  {name}")


def title(ax, text):
    ax.set_title(text, fontsize=11, loc="left", color=INK)


def fig_spider(df):
    base = df[(df.change == 0)].npc.mean()
    groups = [("Prices and money", ["PV price", "Battery price", "Converter price",
                                    "Real discount rate"]),
              ("Demand and technology", ["Annual demand", "Battery cycle life", "PV derating"])]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True)
    for ax, (name, params) in zip(axes, groups):
        ends = []
        for p in params:
            s = df[df.parameter == p].sort_values("change")
            c, ls = LOOK[p]
            y = (s.npc / base - 1) * 100
            ax.plot(s.change * 100, y, color=c, ls=ls, lw=2, marker="o", ms=4)
            if p == "PV derating":          # short line: label its left end, clear of the others
                ax.text(s.change.iloc[0] * 100, y.iloc[0] + 1.2, p, ha="center",
                        fontsize=8.5, color=SLATE)
                continue
            ends.append([p, s.change.iloc[-1] * 100, y.iloc[-1]])
        # spread end labels so they do not overlap
        ends.sort(key=lambda e: e[2])
        for i in range(1, len(ends)):
            ends[i][2] = max(ends[i][2], ends[i - 1][2] + 1.6)
        for p, x, y in ends:
            ax.text(x + 0.8, y, p, va="center", fontsize=8.5, color=SLATE)
        ax.axhline(0, color=MUTE, lw=0.8)
        ax.axvline(0, color=MUTE, lw=0.8)
        ax.set_xlim(-22, 40)
        ax.set_xticks([-20, -10, 0, 10, 20])
        ax.set_xlabel("Change in input (%)")
        title(ax, name)
        style(ax)
    axes[0].set_ylabel("Change in re-optimised NPC (%)")
    fig.suptitle(f"Spider plot  ·  base NPC ₹{base/1e6:.0f} M  ·  every point re-optimised",
                 x=0.01, ha="left", fontsize=11, color=INK)
    save(fig, "sens_spider.png")


def fig_twoway(df):
    n = len(TWOWAY)
    npc = df.pivot(index="batt_factor", columns="pv_factor", values="npc").values / 1e6
    mwh = df.pivot(index="batt_factor", columns="pv_factor", values="batt_strings").values \
        * BATT_KWH_PER_STRING / 1000
    pvmw = df.pivot(index="batt_factor", columns="pv_factor", values="pv_kw").values / 1000
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    for ax, data, label, fmt in [(axes[0], npc, "Re-optimised NPC (₹ million)", "{:.0f}"),
                                 (axes[1], mwh, "Battery the optimiser picks (MWh)", "{:.1f}")]:
        im = ax.imshow(data, cmap=SEQ, origin="lower", aspect="auto")
        for i in range(n):
            for j in range(n):
                txt = fmt.format(data[i, j])
                if ax is axes[1]:
                    txt += f"\n{pvmw[i, j]:.1f} MW PV"
                dark = data[i, j] > np.nanmin(data) + 0.6 * (np.nanmax(data) - np.nanmin(data))
                ax.text(j, i, txt, ha="center", va="center", fontsize=8,
                        color="white" if dark else INK)
        ax.set_xticks(range(n))
        ax.set_xticklabels([f"×{f:g}" for f in TWOWAY])
        ax.set_yticks(range(n))
        ax.set_yticklabels([f"×{f:g}" for f in TWOWAY])
        ax.set_xlabel("PV price")
        ax.set_ylabel("Battery price")
        title(ax, label)
        for s in ax.spines.values():
            s.set_visible(False)
    save(fig, "sens_twoway.png")


def fig_reliability(df):
    ok = df[df.feasible]
    t = ok.target * 100
    base = ok[np.isclose(ok.target, 0.01)].npc.iloc[0]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    a1, a2, a3 = axes
    a1.plot(t, ok.npc / 1e6, color=INK, lw=2, marker="o", ms=5)
    for x, y in zip(t, ok.npc / 1e6):
        a1.text(x * 1.08, y, f"₹{y:.0f} M", fontsize=8, color=SLATE, va="bottom")
    a1.axvline(1, color=UNMET, ls="--", lw=1.2)
    a1.text(1.08, ok.npc.max() / 1e6, "design target", color=UNMET, fontsize=8.5, va="top")
    title(a1, "Cost of reliability")
    a1.set_ylabel("Re-optimised NPC (₹ million)")
    a2.plot(t, ok.pv_kw / 1000, color=FLOW, lw=2, marker="o", ms=5)
    title(a2, "PV the optimiser picks")
    a2.set_ylabel("PV (MW)")
    a3.plot(t, ok.batt_strings * BATT_KWH_PER_STRING / 1000, color=BATT, lw=2, marker="o", ms=5)
    title(a3, "Battery the optimiser picks")
    a3.set_ylabel("Battery (MWh)")
    for ax in axes:
        ax.set_xscale("log")
        ax.set_xticks([0.1, 0.25, 0.5, 1, 2, 5, 10])
        ax.set_xticklabels(["0.1", "0.25", "0.5", "1", "2", "5", "10"])
        ax.set_xlabel("Allowed unmet demand, LPSP (%, log)")
        ax.set_ylim(0, None)
        style(ax)
    tight = ok.iloc[0]
    fig.suptitle(f"Going from 1 % to {tight.target * 100:.1f} % unmet costs "
                 f"{(tight.npc / base - 1) * 100:.0f} % more; relaxing to 10 % saves "
                 f"{(1 - ok.npc.iloc[-1] / base) * 100:.0f} %",
                 x=0.01, ha="left", fontsize=11, color=INK)
    save(fig, "sens_reliability.png")


def fig_montecarlo(df):
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.2), gridspec_kw=dict(width_ratios=[1, 1, 1.1]))
    a1, a2, a3 = axes
    npc = df.npc / 1e6
    p5, p50, p95 = np.percentile(npc, [5, 50, 95])
    a1.hist(npc, bins=40, color=INK, alpha=0.8)
    for v, lab in [(p5, "5 %"), (p50, "median"), (p95, "95 %")]:
        a1.axvline(v, color=ENERGY, lw=1.3, ls="--" if lab != "median" else "-")
        a1.text(v, a1.get_ylim()[1] * 0.97, f" {lab}\n ₹{v:.0f} M", fontsize=8, color=SLATE, va="top")
    a1.set_xlabel("NPC (₹ million)")
    a1.set_ylabel("Samples")
    title(a1, f"NPC: 90 % fall within ₹{p5:.0f}–{p95:.0f} M")
    style(a1)

    lp = df.lpsp * 100
    miss = (df.lpsp > simulator.LPSP_TARGET + 1e-9).mean() * 100
    a2.hist(lp, bins=40, color=UNMET, alpha=0.85)
    a2.axvline(simulator.LPSP_TARGET * 100, color=INK, ls="--", lw=1.3)
    a2.text(simulator.LPSP_TARGET * 100, a2.get_ylim()[1] * 0.97, " 1 % target", fontsize=8.5,
            color=SLATE, va="top")
    a2.set_xlabel("Unmet demand, LPSP (%)")
    title(a2, f"LPSP: target missed in {miss:.0f} % of samples")
    style(a2)

    drivers = list(MC_RANGES) + ["sunshine"]
    labels = list(MC_RANGES) + ["Sunshine (weather year)"]
    rho_npc = [abs(spearmanr(df[d], df.npc)[0]) for d in drivers]
    rho_lp = [abs(spearmanr(df[d], df.lpsp)[0]) for d in drivers]
    order = np.argsort(rho_npc)
    y = np.arange(len(drivers))
    a3.barh(y + 0.2, np.array(rho_npc)[order], 0.38, color=INK, label="NPC")
    a3.barh(y - 0.2, np.array(rho_lp)[order], 0.38, color=UNMET, label="LPSP")
    a3.set_yticks(y)
    a3.set_yticklabels(np.array(labels)[order], fontsize=8.5)
    a3.set_xlim(0, 1)
    a3.set_xlabel("Strength of influence (|Spearman ρ|)")
    title(a3, "What drives each")
    a3.legend(frameon=False, fontsize=9, loc="lower right")
    style(a3)
    fig.suptitle(f"Monte Carlo: {len(df):,} samples, every input uncertain at once, "
                 "design fixed at the optimum", x=0.01, ha="left", fontsize=11, color=INK)
    save(fig, "sens_montecarlo.png")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    design = performance.optimum()
    start = np.array(design, dtype=float)
    print("Spider plot (re-optimising each point)...")
    fig_spider(cached(SPIDER_CSV, lambda: spider(start)))
    print("Two-way PV price x battery price...")
    fig_twoway(cached(TWOWAY_CSV, lambda: twoway(start)))
    print("Reliability target...")
    fig_reliability(cached(RELIABILITY_CSV, lambda: reliability(start)))
    print(f"Monte Carlo, {MC_SAMPLES} samples...")
    mc = cached(MC_CSV, lambda: montecarlo(design))
    fig_montecarlo(mc)
    print(f"\n  NPC 5-95 %: ₹{np.percentile(mc.npc, 5)/1e6:.0f}-{np.percentile(mc.npc, 95)/1e6:.0f} M;"
          f" LPSP target missed in {(mc.lpsp > simulator.LPSP_TARGET + 1e-9).mean():.0%} of samples")
