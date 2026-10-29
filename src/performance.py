"""
Step 10 - Performance study of the optimal off-grid design.

How well does the design the optimiser picked actually perform? Five views:

  weather years   the same design run on 12 years of NASA POWER weather
                  (2013-2024), and the extra cost of a design that meets the
                  1 % LPSP target in every one of them
  shortages       when the unmet energy falls, and how long each shortage lasts
  battery         how hard the battery works: SoC duration curve and
                  equivalent full cycles each month
  PV              specific yield and performance ratio, month by month
  scenarios       off-grid against grid-only and grid + PV on four indicators

Weather files are fetched once from the NASA POWER API into
data/nasa_power_years/ (same point and parameters as data/nasa_power_raw.csv).
The demand profile stays the 2023 one in every weather year.

Outputs
    results/performance_weather.csv
    figures/perf_weather_years.png
    figures/perf_shortages.png
    figures/perf_battery.png
    figures/perf_pv.png
    figures/perf_scenarios.png

Run from the project root, after pso.py and grid_connected.py:
    python src/performance.py
"""

import contextlib
import functools
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import simulator
import pso
import grid_connected
from simulator import simulate, load_inputs, LPSP_TARGET, PENALTY, BATT_KWH_PER_STRING
from prepare_data import read_nasa_power
from costs import PV
from plot_load import style, INK, SLATE, MUTE, FLOW, MONTH_DAYS, MONTH_NAMES

PSO_CSV = "results/pso_runs.csv"
WEATHER_CSV = "results/performance_weather.csv"
WEATHER_DIR = "data/nasa_power_years"
OUT = "figures"

YEARS = list(range(2013, 2025))
DESIGN_YEAR = 2023                     # the year the design was optimised on
NASA_URL = ("https://power.larc.nasa.gov/api/temporal/hourly/point?"
            "parameters=ALLSKY_SFC_SW_DWN,T2M&community=RE&longitude=91.7668"
            "&latitude=26.162&start={y}0101&end={y}1231&format=CSV&time-standard=LST")
ROBUST_PSO = dict(n_particles=20, n_iterations=30)

BATT = "#2a78d6"
UNMET = "#e34948"
WASTE = "#B5BFC3"
GRID = "#6250d6"


# ---------------------------------------------------------------------
# Weather years
# ---------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def weather(year):
    """GHI and temperature for one year, 8760 hours (29 February dropped)."""
    path = f"{WEATHER_DIR}/nasa_{year}.csv"
    if not os.path.exists(path):
        import urllib.request
        os.makedirs(WEATHER_DIR, exist_ok=True)
        urllib.request.urlretrieve(NASA_URL.format(y=year), path)
    df = read_nasa_power(path)
    df = df[~((df.MO == 2) & (df.DY == 29))]
    if len(df) != 8760:
        raise ValueError(f"{path}: {len(df)} hours after dropping 29 Feb")
    return df.ghi.to_numpy(float), df.tamb.to_numpy(float)


@contextlib.contextmanager
def use_weather(year):
    """Run the simulator on another year's weather, with the 2023 demand."""
    base = load_inputs()
    saved = (dict(base), simulator.BATT_FLOAT_LIFE_YEARS)
    ghi, tamb = weather(year)
    simulator._DATA = dict(base, ghi=ghi, tamb=tamb)
    simulator.BATT_FLOAT_LIFE_YEARS = simulator.service_life_years(tamb)
    try:
        yield
    finally:
        simulator._DATA, simulator.BATT_FLOAT_LIFE_YEARS = saved


def optimum():
    runs = pd.read_csv(PSO_CSV)
    b = runs[runs["feasible"]].sort_values("npc").iloc[0]
    return float(b.pv_kw), int(b.batt_strings), float(b.converter_kw), int(b.sc_strings)


def across_years(design):
    """NPC and LPSP of one design in every weather year."""
    pv, nb, conv, sc = design
    out = []
    for y in YEARS:
        with use_weather(y):
            r = simulate(pv, nb, sc, converter_kw=conv, full=True)
            out.append(dict(year=y, npc=r["npc"], lpsp=r["lpsp"],
                            ghi_kwh_m2=simulator._DATA["ghi"].sum() / 1000,
                            batt_life=r["batt_life_years"]))
    return pd.DataFrame(out)


def robust_design(start):
    """Cheapest design (mean NPC over the years) meeting 1 % LPSP in every year."""
    def objective(x):
        rows = across_years((x[0], x[1], x[2], x[3]))
        excess = np.clip(rows.lpsp - LPSP_TARGET, 0, None).sum()
        npc = rows.npc.mean()
        return (npc if excess == 0 else PENALTY * (1 + excess), npc, rows.lpsp.max())
    lo, hi = pso.LO.copy(), pso.HI.copy()
    hi[1] = 800.0                                  # room for a bigger battery
    best, _, _, _, _ = pso.swarm(objective, lo, hi, 1, start=[np.array(start)], **ROBUST_PSO)
    return tuple(best)


def weather_study():
    if os.path.exists(WEATHER_CSV):
        print("  (weather-year results reused from", WEATHER_CSV, "- delete it to recompute)")
        return pd.read_csv(WEATHER_CSV)
    design = optimum()
    print("  running the optimum on 12 weather years, then a design robust to all of them...")
    a = across_years(design).assign(design="optimum")
    rob = robust_design(design)
    b = across_years(rob).assign(design="robust")
    for df, d in ((a, design), (b, rob)):
        df["pv_kw"], df["batt_strings"], df["converter_kw"], df["sc_strings"] = d
    df = pd.concat([a, b], ignore_index=True)
    df.to_csv(WEATHER_CSV, index=False)
    return df


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


def fig_weather_years(df):
    opt, rob = df[df.design == "optimum"], df[df.design == "robust"]
    yrs = opt.year.to_numpy()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.3), gridspec_kw=dict(width_ratios=[1.5, 1]))
    w = 0.38
    a1.bar(yrs - w / 2, opt.lpsp * 100, w, color=UNMET, label=f"optimum for {DESIGN_YEAR}")
    a1.bar(yrs + w / 2, rob.lpsp * 100, w, color=BATT, label="robust to every year")
    a1.axhline(LPSP_TARGET * 100, color=INK, ls="--", lw=1.2)
    a1.text(yrs[0] - 0.6, LPSP_TARGET * 100 + 0.05, "1 % target", fontsize=9, color=SLATE)
    fails = int((opt.lpsp > LPSP_TARGET + 1e-9).sum())
    a1.set_xticks(yrs)
    a1.set_xticklabels([str(y)[2:] for y in yrs])
    a1.set_xlabel("Weather year (20xx)")
    a1.set_ylabel("Unmet demand, LPSP (%)")
    a1.set_ylim(0, max(opt.lpsp.max(), rob.lpsp.max()) * 100 * 1.25)
    title(a1, f"The {DESIGN_YEAR} optimum misses the target in {fails} of {len(yrs)} years")
    a1.legend(frameon=False, fontsize=9, loc="upper left", ncol=2)
    style(a1)

    o, r = opt.iloc[0], rob.iloc[0]
    cost = [opt.npc.mean() / 1e6, rob.npc.mean() / 1e6]
    a2.bar([0, 1], cost, 0.55, color=[UNMET, BATT])
    for i, (c, d) in enumerate([(cost[0], o), (cost[1], r)]):
        a2.text(i, c + 4, f"₹{c:.0f} M\n{d.pv_kw:,.0f} kW PV\n{d.batt_strings * BATT_KWH_PER_STRING / 1000:.1f} MWh",
                ha="center", va="bottom", fontsize=8.5, color=INK)
    a2.set_xticks([0, 1])
    a2.set_xticklabels([f"Optimum for {DESIGN_YEAR}", "Robust to all 12"])
    a2.set_ylim(0, max(cost) * 1.35)
    a2.set_ylabel("Mean NPC over the 12 years (₹ million)")
    title(a2, f"Reliability in every year costs {(cost[1] / cost[0] - 1) * 100:.0f} % more")
    style(a2)
    save(fig, "perf_weather_years.png")


def shortage_events(unmet):
    """Lengths, in hours, of each run of consecutive hours with unmet demand."""
    short = np.r_[0, (unmet > 1e-6).astype(int), 0]
    edges = np.flatnonzero(np.diff(short))
    return edges[1::2] - edges[0::2]


def fig_shortages(r):
    unmet = r["unmet_series"]
    month = np.repeat(np.arange(12), np.array(MONTH_DAYS) * 24)
    grid = np.zeros((12, 24))
    np.add.at(grid, (month, np.arange(len(unmet)) % 24), unmet)
    ev = shortage_events(unmet)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2), gridspec_kw=dict(width_ratios=[1.4, 1]))
    im = a1.imshow(grid / 1000, aspect="auto", cmap="Reds", origin="upper")
    a1.set_yticks(range(12))
    a1.set_yticklabels(MONTH_NAMES)
    a1.set_xticks(range(0, 24, 3))
    a1.set_xlabel("Hour of day")
    cb = fig.colorbar(im, ax=a1, fraction=0.04, pad=0.02)
    cb.set_label("Unmet energy (MWh)")
    title(a1, f"Where the {unmet.sum() / 1000:.0f} MWh of unmet demand falls")
    for s in a1.spines.values():
        s.set_visible(False)

    bins = np.arange(1, ev.max() + 2) - 0.5
    a2.hist(ev, bins=bins, color=UNMET, rwidth=0.85)
    a2.set_xlabel("Shortage length (consecutive hours)")
    a2.set_ylabel("Number of shortages in the year")
    a2.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
    title(a2, f"{len(ev)} shortages, longest {ev.max()} h, median {np.median(ev):.0f} h")
    style(a2)
    save(fig, "perf_shortages.png")
    return ev


def fig_battery(r):
    soc = r["soc_series"] / r["e_batt_kwh"] * 100
    month = np.repeat(np.arange(12), np.array(MONTH_DAYS) * 24)
    out_kwh = r["from_batt_series"] / simulator.CONVERTER["efficiency"]
    efc = np.bincount(month, weights=out_kwh) / r["e_batt_kwh"]

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2))
    srt = np.sort(soc)[::-1]
    a1.plot(np.arange(len(srt)) / len(srt) * 100, srt, color=BATT, lw=2)
    a1.axhline(simulator.BATTERY_LA["soc_min"] * 100, color=MUTE, ls="--", lw=1.2)
    a1.text(2, simulator.BATTERY_LA["soc_min"] * 100 + 2, "20 % floor", fontsize=9, color=SLATE)
    full = (soc > 99).mean() * 100
    a1.text(full + 2, 102, f"full {full:.0f} % of the time", fontsize=9, color=SLATE, va="bottom")
    a1.set_xlim(0, 100)
    a1.set_ylim(0, 112)
    a1.set_xlabel("Share of the year (%)")
    a1.set_ylabel("State of charge at or above (%)")
    title(a1, f"Battery state of charge  ·  {r['e_batt_kwh'] / 1000:.1f} MWh bank")
    style(a1)

    a2.bar(range(12), efc, color=BATT, width=0.7)
    for i, v in enumerate(efc):
        a2.text(i, v + efc.max() * 0.02, f"{v:.0f}", ha="center", fontsize=8, color=SLATE)
    a2.set_xticks(range(12))
    a2.set_xticklabels([m[0] for m in MONTH_NAMES])
    a2.set_ylabel("Equivalent full cycles")
    title(a2, f"{efc.sum():.0f} full cycles a year  ·  life {r['batt_life_years']:.1f} years")
    style(a2)
    save(fig, "perf_battery.png")
    return efc.sum()


def fig_pv(r, pv_kw):
    d = load_inputs()
    month = np.repeat(np.arange(12), np.array(MONTH_DAYS) * 24)
    e_pv = np.bincount(month, weights=r["pv_series"])
    h_ghi = np.bincount(month, weights=d["ghi"]) / 1000            # kWh/m2
    used = np.bincount(month, weights=r["direct_series"] + r["into_batt_series"])
    yield_ = e_pv / pv_kw
    pr = e_pv / (pv_kw * h_ghi)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2))
    a1.bar(range(12), yield_, color=FLOW, width=0.7, label="generated")
    a1.plot(range(12), used / pv_kw, color=INK, marker="o", ms=4, lw=1.4, label="used (rest curtailed)")
    a1.set_xticks(range(12))
    a1.set_xticklabels([m[0] for m in MONTH_NAMES])
    a1.set_ylabel("kWh per kW of PV")
    title(a1, f"Specific yield  ·  {e_pv.sum() / pv_kw:,.0f} kWh/kW a year,"
              f" capacity factor {e_pv.sum() / (pv_kw * 8760) * 100:.1f} %")
    a1.legend(frameon=False, fontsize=9, loc="upper right")
    style(a1)
    a2.plot(range(12), pr * 100, color=FLOW, lw=2, marker="o", ms=5)
    a2.axhline(PV["derating"] * 100, color=MUTE, ls="--", lw=1.2)
    a2.text(0, PV["derating"] * 100 + 0.4, f"derating factor {PV['derating']:.2f}", fontsize=9, color=SLATE)
    a2.set_xticks(range(12))
    a2.set_xticklabels([m[0] for m in MONTH_NAMES])
    a2.set_ylabel("Performance ratio (%)")
    a2.set_ylim(min(pr * 100) - 4, PV["derating"] * 100 + 3)
    title(a2, f"Performance ratio {e_pv.sum() / (pv_kw * h_ghi.sum()) * 100:.1f} %  ·  hot months lose more")
    style(a2)
    save(fig, "perf_pv.png")


def fig_scenarios(r):
    gdf = pd.read_csv(grid_connected.OUT_CSV)
    g = gdf[(gdf.sell == grid_connected.SELL) & (gdf.cap_multiple == 1.0)
            & (gdf.case == "grid + PV")].iloc[0]
    gp = grid_connected.evaluate(g.pv_kw, 0, 0, full=True)
    go = grid_connected.evaluate(0, 0, 0, full=True)
    demand = r["demand"]
    rows = {
        "Off-grid": dict(re=r["served"] / demand * 100, unmet=r["lpsp"] * 100,
                         curt=r["curtailed"] / r["pv_generated"] * 100, lcoe=r["lcoe"]),
        "Grid only": dict(re=0.0, unmet=0.0, curt=0.0, lcoe=go["lcoe"]),
        "Grid + PV": dict(re=gp["res"]["direct"].sum() / demand * 100, unmet=0.0,
                          curt=gp["curtailed"] / gp["res"]["pv"].sum() * 100, lcoe=gp["lcoe"]),
    }
    names = list(rows)
    colors = [BATT, MUTE, FLOW]
    panels = [("re", "Demand met by on-site PV (%)", "{:.0f} %"),
              ("unmet", "Demand not met (%)", "{:.1f} %"),
              ("curt", "PV energy curtailed (%)", "{:.0f} %"),
              ("lcoe", "Cost of electricity (₹/kWh)", "₹{:.2f}")]
    fig, axes = plt.subplots(1, 4, figsize=(13, 3.9))
    for ax, (k, label, fmt) in zip(axes, panels):
        v = [rows[n][k] for n in names]
        ax.bar(range(3), v, color=colors, width=0.65)
        top = max(v) if max(v) > 0 else 1
        for i, x in enumerate(v):
            ax.text(i, x + top * 0.03, fmt.format(x), ha="center", fontsize=8.5, color=INK)
        ax.set_xticks(range(3))
        ax.set_xticklabels(names, fontsize=8.5)
        ax.set_ylim(0, top * 1.22)
        title(ax, label)
        style(ax)
    fig.suptitle(f"Off-grid optimum against the grid options  ·  grid + PV = {g.pv_kw:,.0f} kW, "
                 "export at ₹5.96/kWh up to peak load", x=0.01, ha="left", fontsize=11, color=INK)
    save(fig, "perf_scenarios.png")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    pv, nb, conv, sc = optimum()
    r = simulate(pv, nb, sc, converter_kw=conv, full=True)
    print(f"Optimum: {pv:,.0f} kW PV, {nb} strings, {conv:,.0f} kW converter\n")
    df = weather_study()
    fig_weather_years(df)
    ev = fig_shortages(r)
    efc = fig_battery(r)
    fig_pv(r, pv)
    fig_scenarios(r)

    opt, rob = df[df.design == "optimum"], df[df.design == "robust"]
    print(f"\n  weather years: LPSP {opt.lpsp.min():.2%} to {opt.lpsp.max():.2%},"
          f" fails in {(opt.lpsp > LPSP_TARGET + 1e-9).sum()} of {len(opt)}")
    rr = rob.iloc[0]
    print(f"  robust design: {rr.pv_kw:,.0f} kW PV, {int(rr.batt_strings)} strings,"
          f" {rr.converter_kw:,.0f} kW; mean NPC ₹{rob.npc.mean()/1e6:.1f} M"
          f" vs ₹{opt.npc.mean()/1e6:.1f} M; worst LPSP {rob.lpsp.max():.2%}")
    print(f"  shortages: {len(ev)} events, longest {ev.max()} h")
    print(f"  battery: {efc:.0f} equivalent full cycles a year")
