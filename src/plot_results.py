"""
Results figures for the thesis.

Draws every result figure from the simulator, the grid sweep and the PSO
runs. Each figure is one function, so any of them can be re-run alone.

  npc_landscape.png       NPC over PV x battery, feasible region, optimum
  lpsp_landscape.png      LPSP over PV x battery, 1 % contour
  pareto.png              cheapest NPC for each reliability level
  cost_breakdown.png      where the NPC goes, as a waterfall
  energy_flows.png        where PV energy goes and where demand is met from
  monthly_supply.png      monthly demand by source, and curtailment
  dispatch_days.png       hour-by-hour dispatch on a sunny and a dull day
  soc_year.png            battery state of charge across the year
  soc_cycles.png          rainflow cycle depths of the hourly SoC
  tradeoff.png            battery needed and NPC along the 1 % LPSP boundary
  converter_effect.png    NPC and LPSP against converter rating
  battery_life.png        battery life against bank size
  curtailment.png         curtailment against PV size
  tornado.png             sensitivity of the optimum NPC to each input
  pso_swarm.png           the swarm closing in on the optimum
  solar_resource.png      monthly irradiation and the hourly GHI year
  load_departments.png    demand split by department

Run from the project root, after grid_sweep.py and pso.py:
    python src/plot_results.py
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap, LogNorm
import rainflow

import simulator
import pso
from simulator import simulate, load_inputs, LPSP_TARGET
from costs import PV, BATTERY_LA, CONVERTER, ECON
from plot_load import (style, INK, SLATE, MUTE, ENERGY, FLOW, LINE,
                       MONTH_DAYS, MONTH_NAMES)

OUT = "figures"
GRID_CSV = "results/grid_sweep.csv"
PSO_CSV = "results/pso_runs.csv"
TORNADO_CSV = "results/sensitivity.csv"

# Entity colours, the same in every figure. PV and demand keep the colours
# plot_load.py already uses.
BATT = "#2a78d6"
UNMET = "#e34948"
WASTE = "#B5BFC3"
CAPITAL = "#2a78d6"
LATER = "#eb6834"
CREDIT = "#1baf7a"
SEQ = LinearSegmentedColormap.from_list(
    "blue", ["#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])

DPI = 150


def save(fig, name):
    fig.tight_layout()
    fig.savefig(f"{OUT}/{name}", dpi=DPI)
    plt.close(fig)
    print(f"  {name}")


def title(ax, text):
    ax.set_title(text, fontsize=11, loc="left", color=INK)


def optimum():
    runs = pd.read_csv(PSO_CSV)
    best = runs[runs["feasible"]].sort_values("npc").iloc[0]
    return simulate(best.pv_kw, best.batt_strings, best.sc_strings,
                    converter_kw=best.converter_kw, full=True)


def day_index(month_days=MONTH_DAYS):
    return np.repeat(np.arange(1, 13), month_days)


# ---------------------------------------------------------------------
# Design space
# ---------------------------------------------------------------------

def grid_slice():
    """Grid sweep at the converter rating of its best feasible design."""
    g = pd.read_csv(GRID_CSV)
    best = g[g.lpsp <= LPSP_TARGET].sort_values("npc").iloc[0]
    s = g[g.converter_kw == best.converter_kw]
    npc = s.pivot(index="batt_strings", columns="pv_kw", values="npc")
    lpsp = s.pivot(index="batt_strings", columns="pv_kw", values="lpsp")
    return g, best, npc, lpsp


def edges(v):
    v = np.asarray(v, dtype=float)
    step = v[1] - v[0]
    return np.append(v - step / 2, v[-1] + step / 2)


def fig_npc_landscape(opt):
    g, best, npc, lpsp = grid_slice()
    x, y = npc.columns.values, npc.index.values * 60 / 1000
    feasible = np.where(lpsp.values <= LPSP_TARGET, npc.values / 1e6, np.nan)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.pcolormesh(edges(x), edges(y), np.ones_like(feasible), cmap=plt.matplotlib.colors.ListedColormap(["#EEF1F2"]))
    m = ax.pcolormesh(edges(x), edges(y), feasible, cmap=SEQ.reversed(),
                      vmin=np.nanmin(feasible), vmax=np.nanmin(feasible) * 1.6)
    ax.contour(x, y, lpsp.values, levels=[LPSP_TARGET], colors=INK, linewidths=1.6)
    ax.plot(best.pv_kw, best.batt_kwh / 1000, marker="s", ms=9, mfc="white",
            mec=INK, mew=1.6, ls="none", label=f"Grid optimum  ₹{best.npc/1e6:.1f} M")
    ax.plot(opt["pv_kw"], opt["e_batt_kwh"] / 1000, marker="*", ms=15, mfc=ENERGY,
            mec="white", mew=1.2, ls="none", label=f"PSO optimum  ₹{opt['npc']/1e6:.1f} M")
    ax.text(x[0] + 150, y[2], "LPSP > 1 %\n(infeasible)", color=SLATE, fontsize=9)
    cb = fig.colorbar(m, ax=ax, pad=0.015)
    cb.set_label("Net present cost (₹ million)", color=SLATE)
    cb.ax.tick_params(colors=MUTE, labelsize=8)
    cb.outline.set_edgecolor(LINE)
    ax.set_xlabel("PV capacity (kW)")
    ax.set_ylabel("Battery capacity (MWh)")
    title(ax, f"Cost landscape at {best.converter_kw:.0f} kW converter  ·  line = 1 % LPSP")
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    style(ax)
    ax.grid(False)
    save(fig, "npc_landscape.png")


def fig_lpsp_landscape():
    g, best, npc, lpsp = grid_slice()
    x, y = npc.columns.values, npc.index.values * 60 / 1000
    z = np.clip(lpsp.values * 100, 1e-3, None)

    fig, ax = plt.subplots(figsize=(8, 5))
    m = ax.pcolormesh(edges(x), edges(y), z, cmap=SEQ, norm=LogNorm(vmin=0.05, vmax=z.max()))
    cs = ax.contour(x, y, lpsp.values * 100, levels=[0.5, 1, 2, 5, 10],
                    colors="white", linewidths=1.0)
    ax.clabel(cs, fmt="%g %%", fontsize=8)
    cb = fig.colorbar(m, ax=ax, pad=0.015)
    cb.set_label("LPSP (% of demand unmet)", color=SLATE)
    cb.ax.tick_params(colors=MUTE, labelsize=8)
    cb.outline.set_edgecolor(LINE)
    ax.set_xlabel("PV capacity (kW)")
    ax.set_ylabel("Battery capacity (MWh)")
    title(ax, f"Unmet energy across the design space ({best.converter_kw:.0f} kW converter)")
    style(ax)
    ax.grid(False)
    save(fig, "lpsp_landscape.png")


def fig_pareto():
    g = pd.read_csv(GRID_CSV).sort_values("lpsp")
    front = g.assign(best=g.npc.cummin()).drop_duplicates("best")
    front = front[front.lpsp < 0.2]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.scatter(g.lpsp * 100, g.npc / 1e6, s=6, color=WASTE, alpha=0.6,
               label="All 2,700 swept designs", lw=0)
    ax.step(front.lpsp * 100, front.npc / 1e6, where="post", color=FLOW, lw=2,
            label="Cheapest design at each reliability")
    ax.axvline(LPSP_TARGET * 100, color=ENERGY, ls="--", lw=1.4)
    ax.text(LPSP_TARGET * 100 * 1.08, ax.get_ylim()[1] * 0.97, "1 % target",
            color=ENERGY, fontsize=9, va="top")
    ax.set_xscale("log")
    ax.set_xlim(0.01, 20)
    ax.set_ylim(150, 900)
    ax.set_xlabel("LPSP (% of demand unmet, log scale)")
    ax.set_ylabel("Net present cost (₹ million)")
    title(ax, "The price of reliability")
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    style(ax)
    save(fig, "pareto.png")


# ---------------------------------------------------------------------
# The optimum design
# ---------------------------------------------------------------------

def fig_cost_breakdown(opt):
    p = opt["cost_parts"]
    rows = [("PV capital", p["pv_capital"], CAPITAL),
            ("Battery capital", p["battery_capital"], CAPITAL),
            ("Converter capital", p["converter_capital"], CAPITAL),
            ("Supercapacitor capital", p["sc_capital"], CAPITAL),
            ("Battery replacements", p["battery_replacements"], LATER),
            ("Operation and maintenance", p["om"], LATER),
            ("Salvage credit", p["salvage"], CREDIT)]

    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    run = 0.0
    for i, (name, v, c) in enumerate(rows):
        left = run if v >= 0 else run + v
        ax.barh(i, abs(v) / 1e6, left=left / 1e6, color=c, height=0.62)
        ax.text((run + max(v, 0)) / 1e6 + 6, i, f"{v/1e6:+.1f}", va="center",
                fontsize=9, color=SLATE)
        run += v
    ax.barh(len(rows), run / 1e6, color=INK, height=0.62)
    ax.text(run / 1e6 + 6, len(rows), f"₹{run/1e6:.1f} M", va="center",
            fontsize=9.5, color=INK, fontweight="bold")
    ax.set_yticks(range(len(rows) + 1))
    ax.set_yticklabels([r[0] for r in rows] + ["Net present cost"])
    ax.invert_yaxis()
    ax.set_xlabel("₹ million (present value)")
    ax.set_xlim(0, run / 1e6 * 1.32)
    title(ax, "Where the money goes  ·  blue = up front, orange = over 15 years, green = credit")
    style(ax)
    ax.grid(axis="x", color=LINE, lw=0.8, alpha=0.7)
    ax.grid(axis="y", visible=False)
    save(fig, "cost_breakdown.png")


def fig_energy_flows(opt):
    loss = opt["ac_to_batt"] - opt["batt_to_load"] - (opt["soc_series"][-1] - opt["soc_init"])
    to_store = opt["ac_to_batt"]
    bars = [
        ("PV generation", [("Straight to load", opt["pv_to_load"], FLOW),
                           ("Into battery", to_store, BATT),
                           ("Curtailed", opt["curtailed"], WASTE)]),
        ("Demand", [("From PV directly", opt["pv_to_load"], FLOW),
                    ("From battery", opt["batt_to_load"], BATT),
                    ("Unmet", opt["unmet"], UNMET)]),
        ("Battery path", [("Delivered", opt["batt_to_load"], BATT),
                          ("Losses", loss, MUTE)]),
    ]
    fig, ax = plt.subplots(figsize=(9, 3.8))
    for i, (name, segs) in enumerate(bars):
        left = 0.0
        for label, v, c in segs:
            mwh = v / 1000
            ax.barh(i, mwh, left=left, color=c, height=0.58, edgecolor="white", lw=2)
            if mwh > 180:
                ax.text(left + mwh / 2, i, f"{label}\n{mwh:,.0f} MWh", ha="center",
                        va="center", fontsize=8.5,
                        color="white" if c not in (WASTE,) else INK)
            else:
                ax.text(left + mwh + 30, i - 0.36, f"{label} {mwh:,.0f} MWh",
                        fontsize=8.5, color=SLATE)
            left += mwh
    ax.set_yticks(range(len(bars)))
    ax.set_yticklabels([b[0] for b in bars])
    ax.invert_yaxis()
    ax.set_xlabel("Energy per year (MWh)")
    title(ax, "Annual energy flows at the optimum  ·  losses are in the battery and converter")
    style(ax)
    ax.grid(axis="x", color=LINE, lw=0.8, alpha=0.7)
    ax.grid(axis="y", visible=False)
    save(fig, "energy_flows.png")


def fig_monthly_supply(opt):
    month = np.repeat(day_index(), 24)[:len(opt["load_series"])]
    agg = lambda s: np.array([s[month == m].sum() for m in range(1, 13)]) / 1000
    direct, batt, unmet = (agg(opt["direct_series"]), agg(opt["from_batt_series"]),
                           agg(opt["unmet_series"]))
    curt = agg(opt["pv_series"] - opt["direct_series"] - opt["into_batt_series"])
    x = np.arange(12)

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 6), sharex=True,
                                 gridspec_kw=dict(height_ratios=[2.2, 1]))
    a1.bar(x, direct, 0.66, color=FLOW, label="From PV directly", edgecolor="white", lw=1)
    a1.bar(x, batt, 0.66, bottom=direct, color=BATT, label="From battery", edgecolor="white", lw=1)
    a1.bar(x, unmet, 0.66, bottom=direct + batt, color=UNMET, label="Unmet", edgecolor="white", lw=1)
    for i in range(12):
        if unmet[i] > 1:
            a1.text(i, direct[i] + batt[i] + unmet[i] + 4, f"{unmet[i]:.0f}",
                    ha="center", fontsize=8, color=UNMET)
    a1.set_ylabel("Demand (MWh)")
    title(a1, "How each month's demand is met  ·  red numbers = MWh unmet")
    a1.legend(frameon=False, fontsize=9, ncol=3, loc="upper left")
    style(a1)
    a2.bar(x, curt, 0.66, color=WASTE)
    a2.set_ylabel("Curtailed (MWh)")
    a2.set_xticks(x)
    a2.set_xticklabels(MONTH_NAMES)
    title(a2, "Solar energy thrown away")
    style(a2)
    save(fig, "monthly_supply.png")


def fig_dispatch_days(opt):
    days = len(opt["load_series"]) // 24
    pv_day = opt["pv_series"][:days * 24].reshape(days, 24).sum(1)
    unmet_day = opt["unmet_series"][:days * 24].reshape(days, 24).sum(1)
    sunny = int(pv_day.argmax())
    dull = int(unmet_day.argmax()) if unmet_day.max() > 0 else int(pv_day.argmin())

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, d, name in [(axes[0], sunny, "Sunniest day"), (axes[1], dull, "Worst day for unmet demand")]:
        sl = slice(d * 24, d * 24 + 24)
        h = np.arange(24)
        direct, batt, un = (opt["direct_series"][sl], opt["from_batt_series"][sl],
                            opt["unmet_series"][sl])
        ax.stackplot(h, direct, batt, un, colors=[FLOW, BATT, UNMET],
                     labels=["PV to load", "Battery to load", "Unmet"], alpha=0.9)
        ax.fill_between(h, 0, -opt["into_batt_series"][sl], color=BATT, alpha=0.35,
                        label="PV charging battery", step=None)
        ax.plot(h, opt["pv_series"][sl], color=INK, lw=1.4, ls="--", label="PV output")
        ax.plot(h, opt["load_series"][sl], color=ENERGY, lw=2, label="Demand")
        ax.axhline(0, color=MUTE, lw=0.8)
        ax.set_xticks(range(0, 24, 3))
        ax.set_xlabel("Hour of day")
        m = MONTH_NAMES[day_index()[d] - 1]
        dom = d - np.cumsum([0] + MONTH_DAYS)[day_index()[d] - 1] + 1
        title(ax, f"{name}  ·  {dom} {m}")
        style(ax)
    axes[0].set_ylabel("Power (kW)   ·   below zero = charging")
    axes[0].legend(frameon=False, fontsize=8.5, loc="upper left")
    save(fig, "dispatch_days.png")


def fig_soc_year(opt):
    soc = opt["soc_series"] / opt["e_batt_kwh"] * 100
    days = len(soc) // 24
    d = soc[:days * 24].reshape(days, 24)
    x = np.arange(days)

    fig, ax = plt.subplots(figsize=(11, 4))
    ax.fill_between(x, d.min(1), d.max(1), color=BATT, alpha=0.25, lw=0,
                    label="Daily range")
    ax.plot(x, d.mean(1), color=BATT, lw=1.4, label="Daily mean")
    ax.axhline(BATTERY_LA["soc_min"] * 100, color=UNMET, ls="--", lw=1.2)
    ax.text(2, BATTERY_LA["soc_min"] * 100 + 2, "20 % floor", color=UNMET, fontsize=9)
    cum = np.cumsum([0] + MONTH_DAYS)
    ax.set_xticks(cum[:-1] + np.array(MONTH_DAYS) / 2)
    ax.set_xticklabels(MONTH_NAMES)
    ax.set_xlim(0, days)
    ax.set_ylim(0, 105)
    ax.set_ylabel("State of charge (%)")
    title(ax, f"Battery state of charge through the year  ·  {opt['e_batt_kwh']:,.0f} kWh bank")
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    style(ax)
    save(fig, "soc_year.png")


def fig_soc_cycles(opt):
    soc = opt["soc_series"] / opt["e_batt_kwh"] * 100
    cyc = list(rainflow.count_cycles(soc, binsize=5))
    depth = np.array([c[0] for c in cyc])
    count = np.array([c[1] for c in cyc])

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(depth - 2.5, count, width=4.2, color=BATT, align="center")
    for dpt, c in zip(depth, count):
        if c >= 1:
            ax.text(dpt - 2.5, c + count.max() * 0.015, f"{c:g}", ha="center",
                    fontsize=8, color=SLATE)
    ax.set_xlabel("Cycle depth (% of capacity, 5 % bins)")
    ax.set_ylabel("Cycles per year")
    title(ax, f"Rainflow count of the hourly SoC  ·  {count.sum():.0f} cycles,"
              f" {np.sum(depth * count) / 100:.0f} full-cycle equivalents")
    style(ax)
    save(fig, "soc_cycles.png")


# ---------------------------------------------------------------------
# Trade-offs and sensitivity around the optimum
# ---------------------------------------------------------------------

def min_strings(pv_kw, conv, hi=800):
    """Fewest battery strings meeting the LPSP target at this PV size."""
    if simulate(pv_kw, hi, 4, converter_kw=conv)[1] > LPSP_TARGET:
        return None
    lo = 0
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if simulate(pv_kw, mid, 4, converter_kw=conv)[1] <= LPSP_TARGET:
            hi = mid
        else:
            lo = mid
    return hi


def fig_tradeoff(opt):
    conv = opt["converter_kw"]
    rows = []
    for pv in np.arange(2500, 8001, 250):
        nb = min_strings(pv, conv)
        if nb is None:
            continue
        npc = simulate(pv, nb, 4, converter_kw=conv)[0]
        rows.append((pv, nb * 60 / 1000, npc / 1e6))
    pv, mwh, npc = map(np.array, zip(*rows))

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2))
    a1.plot(pv, mwh, color=BATT, lw=2, marker="o", ms=4)
    a1.set_xlabel("PV capacity (kW)")
    a1.set_ylabel("Battery needed (MWh)")
    title(a1, "Smallest battery that meets 1 % LPSP")
    style(a1)
    a2.plot(pv, npc, color=INK, lw=2, marker="o", ms=4)
    i = npc.argmin()
    a2.plot(pv[i], npc[i], marker="*", ms=15, color=ENERGY, mec="white")
    a2.text(pv[i] + 150, npc[i] + (npc.max() - npc.min()) * 0.05,
            f"{pv[i]:,.0f} kW · ₹{npc[i]:.1f} M", ha="left", va="bottom",
            fontsize=9, color=INK)
    a2.set_xlabel("PV capacity (kW)")
    a2.set_ylabel("Net present cost (₹ million)")
    title(a2, "NPC along that boundary")
    style(a2)
    save(fig, "tradeoff.png")


def fig_converter(opt):
    conv = np.arange(300, 2501, 100)
    r = [simulate(opt["pv_kw"], opt["n_batt_strings"], 4, converter_kw=c) for c in conv]
    npc = np.array([x[0] for x in r]) / 1e6
    lpsp = np.array([x[1] for x in r]) * 100
    infeasible = conv[lpsp > LPSP_TARGET * 100]
    edge = infeasible.max() + 50 if len(infeasible) else None

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    if edge:
        for a in (a1, a2):
            a.axvspan(conv[0] - 100, edge, color=UNMET, alpha=0.07, lw=0)
        a2.text(conv[0], npc.max(), "LPSP > 1 %\ncheaper but\ninfeasible",
                fontsize=8.5, color=UNMET, va="top")
    a1.plot(conv, lpsp, color=UNMET, lw=2)
    a1.axhline(LPSP_TARGET * 100, color=ENERGY, ls="--", lw=1.3)
    a1.axvline(simulator.default_converter_kw(), color=MUTE, ls=":", lw=1.3)
    a1.text(simulator.default_converter_kw() + 30, lpsp.max() * 0.9,
            "old fixed rule\n1.1 × peak load", fontsize=8.5, color=SLATE)
    a1.set_xlabel("Converter rating (kW)")
    a1.set_ylabel("LPSP (%)")
    title(a1, "A small converter starves the battery")
    style(a1)
    a2.plot(conv, npc, color=INK, lw=2)
    a2.axvline(opt["converter_kw"], color=ENERGY, ls="--", lw=1.3)
    a2.text(opt["converter_kw"] + 30, npc.max() * 0.995,
            f"optimum {opt['converter_kw']:,.0f} kW", fontsize=8.5, color=ENERGY, va="top")
    a2.set_xlabel("Converter rating (kW)")
    a2.set_ylabel("Net present cost (₹ million)")
    title(a2, f"NPC at {opt['pv_kw']:,.0f} kW PV, {opt['e_batt_kwh']:,.0f} kWh")
    style(a2)
    save(fig, "converter_effect.png")


def fig_battery_life(opt):
    strings = np.arange(40, 601, 20)
    life, lpsp = [], []
    for nb in strings:
        r = simulate(opt["pv_kw"], nb, 4, converter_kw=opt["converter_kw"], full=True)
        life.append(r["batt_life_years"])
        lpsp.append(r["lpsp"])
    mwh = strings * 60 / 1000

    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(mwh, life, color=BATT, lw=2, marker="o", ms=4)
    ax.axhline(simulator.BATT_FLOAT_LIFE_YEARS, color=MUTE, ls="--", lw=1.2)
    ax.text(mwh[0], simulator.BATT_FLOAT_LIFE_YEARS + 0.2, "float life limit",
            color=SLATE, fontsize=9)
    ax.axvline(opt["e_batt_kwh"] / 1000, color=ENERGY, ls=":", lw=1.3)
    ax.text(opt["e_batt_kwh"] / 1000 + 0.3, 1, "optimum", color=ENERGY, fontsize=9)
    ax.set_ylim(0, simulator.BATT_FLOAT_LIFE_YEARS + 1.5)
    ax.set_xlabel("Battery capacity (MWh)")
    ax.set_ylabel("Battery life (years)")
    title(ax, f"Bigger banks cycle less and last longer  ·  PV {opt['pv_kw']:,.0f} kW")
    style(ax)
    save(fig, "battery_life.png")


def fig_curtailment(opt):
    pvs = np.arange(1500, 8001, 250)
    frac, lpsp = [], []
    for p in pvs:
        r = simulate(p, opt["n_batt_strings"], 4, converter_kw=opt["converter_kw"], full=True)
        frac.append(r["curtailed"] / r["pv_generated"] * 100)
        lpsp.append(max(r["lpsp"] * 100, 1e-3))     # floor: below this is rounding noise

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4))
    a1.plot(pvs, frac, color=MUTE, lw=2)
    a1.set_xlabel("PV capacity (kW)")
    a1.set_ylabel("Curtailed (% of PV output)")
    title(a1, "Curtailment grows with every extra kW")
    a2.plot(pvs, lpsp, color=UNMET, lw=2)
    a2.axhline(LPSP_TARGET * 100, color=ENERGY, ls="--", lw=1.3)
    a2.set_yscale("log")
    a2.set_ylim(5e-4, 100)
    zero = pvs[np.array(lpsp) <= 1e-3]
    if len(zero):
        a2.text(zero[0], 2e-3, f"no unmet energy\nfrom {zero[0]:,.0f} kW", fontsize=8.5,
                color=SLATE)
    a2.set_xlabel("PV capacity (kW)")
    a2.set_ylabel("LPSP (%, log scale)")
    title(a2, "...while unmet energy falls ever more slowly")
    for a in (a1, a2):
        a.axvline(opt["pv_kw"], color=ENERGY, ls=":", lw=1.3)
        style(a)
    save(fig, "curtailment.png")


def reoptimise():
    """Cheapest feasible design under the current parameters (one PSO run)."""
    bounds = [b if b[0] != "sc_strings" else ("sc_strings", 4.0, 4.0) for b in pso.BOUNDS]
    res, _ = pso.run_pso(4, bounds=bounds, n_particles=20, n_iterations=30)
    return res["npc"] if res["feasible"] else np.nan


def fig_tornado():
    d = load_inputs()
    base_load = d["load"].copy()

    def scale_load(f):
        d["load"] = base_load * f

    tests = []
    for label, keys, lo, hi in [
            ("PV price", [(PV, "capital_inr_per_kw"), (PV, "replacement_inr_per_kw")], 0.8, 1.2),
            ("Battery price", [(BATTERY_LA, "capital_inr_per_unit"),
                               (BATTERY_LA, "replacement_inr_per_unit")], 0.8, 1.2),
            ("Converter price", [(CONVERTER, "capital_inr_per_kw"),
                                 (CONVERTER, "replacement_inr_per_kw")], 0.8, 1.2),
            ("Real discount rate", [(ECON, "real_discount")], 0.8, 1.2),
            ("PV derating factor", [(PV, "derating")], 0.94, 1.06)]:
        tests.append((label, keys, lo, hi))

    if os.path.exists(TORNADO_CSV):
        df = pd.read_csv(TORNADO_CSV)
        print("  (sensitivity results reused from", TORNADO_CSV, "- delete it to recompute)")
    else:
        print("  re-optimising for each sensitivity case (about 2 minutes)...")
        base = reoptimise()
        rows = []
        for label, keys, lo, hi in tests:
            out = []
            for f in (lo, hi):
                origs = [c[k] for c, k in keys]
                for c, k in keys:
                    c[k] = c[k] * f
                out.append(reoptimise())
                for (c, k), o in zip(keys, origs):
                    c[k] = o
            rows.append(dict(parameter=label, low=f"{lo:.2f}x", high=f"{hi:.2f}x",
                             npc_low=out[0], npc_high=out[1], npc_base=base))
        # battery cycle life and room temperature live in the simulator module
        orig = simulator.BATT_CYCLE_LIFE
        out = []
        for f in (0.8, 1.2):
            simulator.BATT_CYCLE_LIFE = tuple((dod, n * f) for dod, n in orig)
            out.append(reoptimise())
        simulator.BATT_CYCLE_LIFE = orig
        rows.append(dict(parameter="Battery cycle life", low="0.80x", high="1.20x",
                         npc_low=out[0], npc_high=out[1], npc_base=base))
        orig = simulator.BATT_FLOAT_LIFE_YEARS
        out = []
        for dt in (-3.0, 3.0):
            simulator.BATT_FLOAT_LIFE_YEARS = simulator.service_life_years(
                d["tamb"], simulator.BATT_ROOM_OFFSET_C + dt)
            out.append(reoptimise())
        simulator.BATT_FLOAT_LIFE_YEARS = orig
        rows.append(dict(parameter="Battery room temperature", low="−3 °C", high="+3 °C",
                         npc_low=out[0], npc_high=out[1], npc_base=base))
        out = []
        for f in (0.9, 1.1):
            scale_load(f)
            out.append(reoptimise())
        scale_load(1.0)
        rows.append(dict(parameter="Annual demand", low="0.90x", high="1.10x",
                         npc_low=out[0], npc_high=out[1], npc_base=base))
        df = pd.DataFrame(rows)
        df.to_csv(TORNADO_CSV, index=False)

    base = df.npc_base.iloc[0] / 1e6
    df = df.assign(span=(df.npc_high - df.npc_low).abs()).sort_values("span")
    fig, ax = plt.subplots(figsize=(9, 4.4))
    for i, r in enumerate(df.itertuples()):
        cases = [(r.npc_low / 1e6, r.low, FLOW, r.npc_high / 1e6),
                 (r.npc_high / 1e6, r.high, ENERGY, r.npc_low / 1e6)]
        for v, lab, c, other in cases:
            ax.barh(i, v - base, left=base, color=c, height=0.6)
            # an unchanged case goes on the side its partner leaves free
            right = v > base + 0.05 or (abs(v - base) <= 0.05 and other < base)
            ax.text(v + (1.2 if right else -1.2), i, f"{lab}  ₹{v:.0f} M",
                    va="center", ha="left" if right else "right", fontsize=8.5, color=SLATE)
    ax.axvline(base, color=INK, lw=1.2)
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df.parameter)
    span = max(abs(df.npc_low / 1e6 - base).max(), abs(df.npc_high / 1e6 - base).max())
    ax.set_xlim(base - span * 1.6, base + span * 1.6)
    ax.set_xlabel("Re-optimised net present cost (₹ million)")
    title(ax, f"Sensitivity of the optimum  ·  base ₹{base:.0f} M  ·  teal = input lowered, orange = raised")
    style(ax)
    ax.grid(axis="x", color=LINE, lw=0.8, alpha=0.7)
    ax.grid(axis="y", visible=False)
    save(fig, "tornado.png")


def fig_swarm():
    g, best, npc, lpsp = grid_slice()
    x, y = npc.columns.values, npc.index.values * 60 / 1000
    feasible = np.where(lpsp.values <= LPSP_TARGET, npc.values / 1e6, np.nan)
    bounds = [b if b[0] != "sc_strings" else ("sc_strings", 4.0, 4.0) for b in pso.BOUNDS]
    res, _ = pso.run_pso(4, bounds=bounds, record=True)
    trail = res["trail"]
    snaps = [0, 3, 10, len(trail) - 1]

    fig, axes = plt.subplots(1, 4, figsize=(13, 3.8), sharey=True)
    for ax, k in zip(axes, snaps):
        ax.pcolormesh(edges(x), edges(y), feasible, cmap=SEQ.reversed(),
                      vmin=np.nanmin(feasible), vmax=np.nanmin(feasible) * 1.6)
        ax.contour(x, y, lpsp.values, levels=[LPSP_TARGET], colors=INK, linewidths=1.2)
        p = trail[k]
        ax.scatter(p[:, 0], p[:, 1] * 60 / 1000, s=22, color=ENERGY, edgecolor="white",
                   lw=0.8, zorder=3)
        ax.set_xlim(1000, 8000)
        ax.set_ylim(0, 30)
        ax.set_xlabel("PV (kW)")
        title(ax, f"Iteration {k}")
        style(ax)
        ax.grid(False)
    axes[0].set_ylabel("Battery (MWh)")
    fig.suptitle("The swarm converging on the cheapest feasible region (seed 4)",
                 x=0.01, ha="left", fontsize=11, color=INK)
    save(fig, "pso_swarm.png")


# ---------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------

def fig_solar():
    d = load_inputs()
    ghi = d["ghi"]
    days = len(ghi) // 24
    month = day_index()
    daily = ghi[:days * 24].reshape(days, 24)
    monthly = np.array([daily[month == m].sum() for m in range(1, 13)]) / 1000

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4), gridspec_kw=dict(width_ratios=[1, 1.6]))
    a1.bar(range(12), monthly, 0.66, color=FLOW)
    for i, v in enumerate(monthly):
        a1.text(i, v + 2, f"{v:.0f}", ha="center", fontsize=8, color=SLATE)
    a1.set_xticks(range(12))
    a1.set_xticklabels([m[0] for m in MONTH_NAMES])
    a1.set_ylabel("Irradiation (kWh/m²)")
    title(a1, f"Monthly sunshine  ·  {monthly.sum():,.0f} kWh/m² a year")
    style(a1)
    sun = LinearSegmentedColormap.from_list("sun", ["#FFFFFF", "#F6D7A7", "#E89A3C", "#B35C06", "#5E2F02"])
    im = a2.imshow(daily.T, aspect="auto", origin="lower", cmap=sun, extent=[0, days, 0, 24])
    cum = np.cumsum([0] + MONTH_DAYS)
    a2.set_xticks(cum[:-1] + np.array(MONTH_DAYS) / 2)
    a2.set_xticklabels(MONTH_NAMES)
    a2.set_yticks(range(0, 25, 6))
    a2.set_ylabel("Hour of day")
    title(a2, "Hourly irradiance across 2023 (W/m²)  ·  pale streaks are cloudy days")
    a2.tick_params(colors=MUTE, labelsize=9)
    cb = fig.colorbar(im, ax=a2, pad=0.015)
    cb.ax.tick_params(colors=MUTE, labelsize=8)
    cb.outline.set_edgecolor(LINE)
    save(fig, "solar_resource.png")


def fig_departments():
    df = pd.read_csv(simulator.INPUT_FILE)
    cols = [c for c in df.columns if c.startswith("dept_")]
    names = {"dept_mechanical": "Mechanical + Central Workshop",
             "dept_electronics": "Electronics and Electrical"}
    colors = [FLOW, BATT]
    n = len(df)
    hod = np.arange(n) % 24
    dow = (np.arange(n) // 24 + 6) % 7          # 1 Jan 2023 was a Sunday
    wk = dow < 5
    month = np.repeat(day_index(), 24)[:n]

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2))
    prof = [np.array([df[c][wk & (hod == h)].mean() for h in range(24)]) for c in cols]
    a1.stackplot(range(24), *prof, colors=colors,
                 labels=[names.get(c, c) for c in cols], alpha=0.9)
    a1.set_xticks(range(0, 24, 3))
    a1.set_xlabel("Hour of day")
    a1.set_ylabel("Mean weekday demand (kW)")
    a1.set_ylim(0, max(sum(prof)) * 1.3)
    title(a1, "Average weekday by department")
    a1.legend(frameon=False, fontsize=8.5, loc="upper left", ncol=2)
    style(a1)
    bottom = np.zeros(12)
    for c, col in zip(cols, colors):
        v = np.array([df[c][month == m].sum() for m in range(1, 13)]) / 1000
        a2.bar(range(12), v, 0.66, bottom=bottom, color=col, edgecolor="white", lw=1)
        bottom += v
    a2.set_xticks(range(12))
    a2.set_xticklabels([m[0] for m in MONTH_NAMES])
    a2.set_ylabel("Energy (MWh)")
    title(a2, "Monthly demand  ·  dips are the two vacations")
    style(a2)
    save(fig, "load_departments.png")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for f in (GRID_CSV, PSO_CSV):
        if not os.path.exists(f):
            raise FileNotFoundError(f"{f} not found - run grid_sweep.py and pso.py first")
    opt = optimum()
    print(f"Optimum: PV {opt['pv_kw']:,.0f} kW, {opt['e_batt_kwh']:,.0f} kWh,"
          f" converter {opt['converter_kw']:,.0f} kW, NPC ₹{opt['npc']/1e6:.1f} M\n")
    fig_npc_landscape(opt)
    fig_lpsp_landscape()
    fig_pareto()
    fig_cost_breakdown(opt)
    fig_energy_flows(opt)
    fig_monthly_supply(opt)
    fig_dispatch_days(opt)
    fig_soc_year(opt)
    fig_soc_cycles(opt)
    fig_tradeoff(opt)
    fig_converter(opt)
    fig_battery_life(opt)
    fig_curtailment(opt)
    fig_swarm()
    fig_solar()
    fig_departments()
    fig_tornado()
    print(f"\n  figures written to {OUT}/")
