"""
Step 4 - Coarse grid sweep.

Tries a grid of designs, filters to those meeting the reliability target,
and reports the cheapest. This is the benchmark PSO gets checked against.

Also produces figures/monthly_balance.png, which shows why this site is
hard to size for.

Run from the project root:
    python src/grid_sweep.py
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from simulator import simulate, load_inputs, LPSP_TARGET, pv_output_kw
from costs import ECON

OUT_CSV = "results/grid_sweep.csv"
FIG = "figures/monthly_balance.png"

# search grid
PV_KW = np.arange(1500, 7001, 500)          # 12 values
BATT_STRINGS = np.arange(20, 501, 20)       # 25 values
CONVERTER_KW = np.arange(600, 2201, 200)    # 9 values
SC_STRINGS = 4                              # fixed at the transient requirement


def sweep():
    rows = []
    total = len(PV_KW) * len(BATT_STRINGS) * len(CONVERTER_KW)
    print(f"Evaluating {total} designs...")

    for i, pv in enumerate(PV_KW):
        for nb in BATT_STRINGS:
            for conv in CONVERTER_KW:
                npc, lpsp, score = simulate(pv, nb, SC_STRINGS, converter_kw=conv)
                rows.append(dict(pv_kw=pv, batt_strings=nb,
                                 batt_kwh=nb * 60, converter_kw=conv,
                                 sc_strings=SC_STRINGS,
                                 npc=npc, lpsp=lpsp, score=score))
        done = (i + 1) * len(BATT_STRINGS) * len(CONVERTER_KW)
        print(f"  PV = {pv} kW done ({done}/{total})")

    df = pd.DataFrame(rows)
    os.makedirs("results", exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    return df


def report(df):
    feasible = df[df["lpsp"] <= LPSP_TARGET]
    print(f"\n{len(feasible)} of {len(df)} designs meet LPSP <= {LPSP_TARGET*100:.0f}%")

    if feasible.empty:
        print("  none feasible - widen the grid upward")
        best = df.sort_values("lpsp").iloc[0]
        print(f"  closest: PV {best.pv_kw:.0f} kW, {best.batt_kwh:.0f} kWh,"
              f" LPSP {best.lpsp*100:.2f}%")
        return None

    best = feasible.sort_values("npc").iloc[0]
    print("\n  === cheapest feasible design ===")
    print(f"  PV                 {best.pv_kw:,.0f} kW")
    print(f"  battery            {best.batt_strings:.0f} strings"
          f" = {best.batt_kwh:,.0f} kWh")
    print(f"  converter          {best.converter_kw:,.0f} kW")
    print(f"  supercapacitor     {best.sc_strings:.0f} strings")
    print(f"  LPSP               {best.lpsp*100:.3f} %")
    print(f"  NPC                {best.npc/1e6:,.1f} M INR")

    full = simulate(best.pv_kw, best.batt_strings, best.sc_strings,
                    converter_kw=best.converter_kw, full=True)
    print(f"  salvage credit     {full['salvage']/1e6:,.1f} M INR (in the NPC)")
    print(f"  LCOE               {full['lcoe']:.2f} INR/kWh")
    print(f"  curtailed          {full['curtailed']:,.0f} kWh/yr"
          f"  ({full['curtailed']/full['pv_generated']*100:.1f}% of generation)")
    print(f"  battery life       {full['batt_life_years']:.1f} years")

    print("\n  --- five cheapest feasible ---")
    top5 = feasible.sort_values("npc").head(5)
    for _, r in top5.iterrows():
        print(f"    PV {r.pv_kw:5.0f} kW  batt {r.batt_kwh:6.0f} kWh"
              f"  conv {r.converter_kw:5.0f} kW"
              f"  LPSP {r.lpsp*100:5.2f}%  NPC {r.npc/1e6:7.1f} M")

    # how flat is the basin? if the top designs differ a lot in shape but
    # little in cost, the optimum is weakly determined and prices will move it
    spread = (top5.npc.max() - top5.npc.min()) / top5.npc.min() * 100
    print(f"\n  cost spread across the five cheapest: {spread:.1f} %")
    print(f"  their PV range:      {top5.pv_kw.min():.0f} - {top5.pv_kw.max():.0f} kW")
    print(f"  their battery range: {top5.batt_kwh.min():.0f} - {top5.batt_kwh.max():.0f} kWh")
    print(f"  their converter range: {top5.converter_kw.min():.0f}"
          f" - {top5.converter_kw.max():.0f} kW")

    # --- boundary check: an optimum on the edge of the grid is not an optimum
    print("\n  --- boundary check ---")
    edge = False
    for name, val, lo, hi in [("PV", best.pv_kw, PV_KW[0], PV_KW[-1]),
                              ("battery strings", best.batt_strings,
                               BATT_STRINGS[0], BATT_STRINGS[-1]),
                              ("converter kW", best.converter_kw,
                               CONVERTER_KW[0], CONVERTER_KW[-1])]:
        on_edge = (val <= lo) or (val >= hi)
        edge = edge or on_edge
        flag = "ON THE EDGE - widen the grid" if on_edge else "interior, fine"
        print(f"    {name:<16s} {val:7.0f}   range [{lo:.0f}, {hi:.0f}]   {flag}")
    if not edge:
        print("    optimum is interior to the grid on every axis")
    return best


def monthly_figure(best):
    """Monthly energy balance, plus the worst run of consecutive dull days -
    which is what actually sizes the battery here."""
    d = load_inputs()
    pv = pv_output_kw(best.pv_kw, d["ghi"], d["tamb"])
    month = np.repeat(np.arange(1, 13),
                      [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]) \
        .repeat(24)[:d["n"]]

    gen = np.array([pv[month == m].sum() for m in range(1, 13)]) / 1000
    dem = np.array([d["load"][month == m].sum() for m in range(1, 13)]) / 1000

    names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
             "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    x = np.arange(12)

    os.makedirs("figures", exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(x - 0.2, gen, 0.4, label="PV generation", color="#1F7A72")
    ax.bar(x + 0.2, dem, 0.4, label="Demand", color="#C86A0A")
    ax.set_xticks(x); ax.set_xticklabels(names)
    ax.set_ylabel("Energy (MWh)")
    ax.set_title(f"Monthly generation vs demand  —  PV {best.pv_kw:.0f} kW, "
                 f"{best.batt_kwh:.0f} kWh battery")
    ax.legend(frameon=False)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG, dpi=150)
    print(f"\n  wrote {FIG}")

    surplus = gen - dem
    print("  monthly surplus (MWh): " +
          ", ".join(f"{names[i]} {surplus[i]:+.0f}" for i in range(12)))

    if (surplus > 0).all():
        print("  every month is in surplus - the shortfall is NOT seasonal")

    # --- what actually sizes the battery: the worst run of dull days ---
    daily_gen = pv.reshape(-1, 24).sum(axis=1)
    daily_dem = d["load"].reshape(-1, 24).sum(axis=1)
    daily_net = daily_gen - daily_dem

    worst_len, worst_start, worst_deficit = 0, 0, 0.0
    run_len, run_start, run_sum = 0, 0, 0.0
    for i, v in enumerate(daily_net):
        if v < 0:
            if run_len == 0:
                run_start = i
            run_len += 1
            run_sum += v
            if run_sum < worst_deficit:
                worst_len, worst_start, worst_deficit = run_len, run_start, run_sum
        else:
            run_len, run_sum = 0, 0.0

    autonomy = best.batt_kwh * 0.8 / (daily_dem.mean())
    print(f"\n  worst run of deficit days: {worst_len} consecutive days"
          f" starting day {worst_start + 1}")
    print(f"  cumulative deficit over it: {-worst_deficit:,.0f} kWh")
    print(f"  chosen battery usable:      {best.batt_kwh * 0.8:,.0f} kWh"
          f"  ({autonomy:.1f} days of autonomy)")

    if worst_len >= 2 and autonomy > 1.0:
        print("  -> the battery is sized by consecutive dull days,"
              " not by the daily cycle")
    elif autonomy < 1.0:
        print("  -> under one day of autonomy: the battery is sized by the"
              " overnight cycle, and reliability comes from oversized PV")
    else:
        print("  -> deficit days are isolated rather than clustered here")


if __name__ == "__main__":
    df = sweep()
    best = report(df)
    if best is not None:
        monthly_figure(best)
