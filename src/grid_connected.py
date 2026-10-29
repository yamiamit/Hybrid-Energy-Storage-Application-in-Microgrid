"""
Step 9 - Grid-connected scenario.

Kumar et al. compare off-grid designs with grid-connected ones. Here the
same site is connected to the grid at the Assam commercial tariff: PV serves
the load first, surplus is exported up to the connection's limit, and any
shortfall is imported. Nothing is ever unmet, so there is no LPSP
constraint and no supercapacitor (the grid absorbs the 93 kW step).

Four cases are compared, each at its own optimum:
  off-grid           the single-year PSO optimum from pso.py
  grid only          buy everything, build nothing
  grid + PV          PV size optimised
  grid + PV + battery PV, battery and converter optimised by PSO

PV costs about 4.3 INR/kWh over its life, less than the 5.96 INR/kWh grid
tariff. With unlimited export at that price, more PV always pays and there
is no optimum, so export is capped (EXPORT_CAP_KW). The export price and the
cap are both varied, because neither is fixed by the paper.

The battery stores surplus only when exporting it is worth less than using
it later: sell price < buy price x round-trip efficiency.

Outputs
    results/grid_connected.csv   optimum of each case at each export price
    figures/grid_scenarios.png   NPC and LCOE of the four cases
    figures/grid_feedin.png      optimal PV and NPC against export price and cap
    figures/grid_battery.png     NPC against battery size on the grid
    figures/grid_dispatch.png    import and export on a sunny and a dull day

Run from the project root, after pso.py:
    python src/grid_connected.py
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from costs import BATTERY_LA, CONVERTER, ECON
from simulator import (load_inputs, pv_output_kw, compute_npc, battery_life_years, crf,
                       BATT_KWH_PER_STRING, BATT_CHARGE_KW_PER_STRING,
                       BATT_DISCHARGE_KW_PER_STRING)
import pso
from plot_load import style, INK, SLATE, MUTE, ENERGY, FLOW

PSO_CSV = "results/pso_runs.csv"
OUT_CSV = "results/grid_connected.csv"
OUT = "figures"

# =====================================================================
# CONFIG
# =====================================================================

BUY = ECON["grid_buy_inr_per_kwh"]             # 5.96, Assam commercial rate
SELL = ECON["grid_sell_inr_per_kwh"]           # paper assumes sell = buy
SELL_PRICES = [0.0, 1.5, 3.0, 4.5, SELL]       # export price sweep, INR/kWh
CAP_MULTIPLES = [0.5, 1.0, 2.0]                # export cap as a multiple of peak load

PV_SWEEP = np.arange(0, 12001, 100)            # kW, for the grid + PV case
BOUNDS = [("pv_kw", 0.0, 12000.0), ("batt_strings", 0.0, 300.0),
          ("converter_kw", 0.0, 3000.0)]
PSO_SIZE = dict(n_particles=20, n_iterations=40)
SEED = 1

GRID = "#6250d6"          # imports and exports; PV and battery keep their colours
BATT = "#2a78d6"
UNMET = "#e34948"

R = ECON["real_discount"]
YEARS = ECON["project_years"]
ANNUITY = 1.0 / crf(R, YEARS)                  # present value of 1 INR a year

# =====================================================================


def export_cap_kw(multiple=1.0):
    """Export limit: the grid connection is sized for the peak load."""
    return multiple * load_inputs()["load"].max()


def run_grid(pv_kw, n_strings, conv_kw, sell=SELL, cap_kw=None):
    """One year on the grid, hour by hour. Returns flows and the SoC series."""
    d = load_inputs()
    load, n = d["load"], d["n"]
    pv = pv_output_kw(pv_kw, d["ghi"], d["tamb"])
    cap = export_cap_kw() if cap_kw is None else cap_kw

    direct = np.minimum(pv, load)
    surplus = pv - direct
    deficit = load - direct

    e_batt = n_strings * BATT_KWH_PER_STRING
    if n_strings == 0:
        exp = np.minimum(surplus, cap)
        imp = deficit
        soc = np.zeros(n)
        into = out = np.zeros(n)
        throughput = 0.0
    else:
        eta_b = np.sqrt(BATTERY_LA["roundtrip_efficiency"])
        eta_c = CONVERTER["efficiency"]
        store_first = sell < BUY * BATTERY_LA["roundtrip_efficiency"] * eta_c ** 2
        p_chg = n_strings * BATT_CHARGE_KW_PER_STRING
        p_dis = n_strings * BATT_DISCHARGE_KW_PER_STRING
        lo, hi = BATTERY_LA["soc_min"] * e_batt, e_batt
        s = BATTERY_LA["soc_init"] * e_batt
        soc, into, out, exp, imp = (np.zeros(n) for _ in range(5))
        throughput = 0.0
        for t in range(n):
            if surplus[t] > 0.0:
                spare = surplus[t] if store_first else max(0.0, surplus[t] - cap)
                terminal = min(spare * eta_c, conv_kw * eta_c, p_chg, (hi - s) / eta_b)
                ac_in = terminal / eta_c if eta_c > 0 else 0.0
                s += terminal * eta_b
                into[t] = ac_in
                exp[t] = min(surplus[t] - ac_in, cap)
            elif deficit[t] > 0.0:
                terminal = min(deficit[t] / eta_c, conv_kw / eta_c, p_dis, (s - lo) * eta_b)
                ac_out = terminal * eta_c
                s -= terminal / eta_b
                out[t] = ac_out
                throughput += terminal
                imp[t] = deficit[t] - ac_out
            soc[t] = s

    return dict(pv=pv, load=load, direct=direct, into=into, out=out, exp=exp, imp=imp,
                curtailed=surplus - into - exp, soc_series=soc, e_batt=e_batt,
                throughput=throughput)


def evaluate(pv_kw, n_strings, conv_kw, sell=SELL, cap_kw=None, full=False):
    """NPC of a grid-connected design: equipment plus 15 years of grid bills."""
    pv_kw, n_strings, conv_kw = max(0.0, pv_kw), max(0, int(round(n_strings))), max(0.0, conv_kw)
    if n_strings == 0:
        conv_kw = 0.0
    res = run_grid(pv_kw, n_strings, conv_kw, sell, cap_kw)
    life = battery_life_years(n_strings, res)
    built = pv_kw > 0 or n_strings > 0
    npc_kit, _, _, _, parts = compute_npc(pv_kw, n_strings, 0, conv_kw, life)
    if not built:                      # grid only: no microgrid, so no fixed O&M
        npc_kit = 0.0
        parts = {k: 0.0 for k in parts}
    bill = res["imp"].sum() * BUY - res["exp"].sum() * sell
    npc = npc_kit + bill * ANNUITY
    if not full:
        return npc
    served = res["load"].sum()
    return dict(npc=npc, lcoe=npc * crf(R, YEARS) / served, parts=parts,
                grid_bill_npc=bill * ANNUITY, imported=res["imp"].sum(),
                exported=res["exp"].sum(), curtailed=res["curtailed"].sum(),
                batt_life=life, res=res, pv_kw=pv_kw, n_strings=n_strings,
                converter_kw=conv_kw)


# ---------------------------------------------------------------------
# Optimisation
# ---------------------------------------------------------------------

def best_pv(sell=SELL, cap_kw=None):
    npc = [evaluate(p, 0, 0, sell, cap_kw) for p in PV_SWEEP]
    i = int(np.argmin(npc))
    return float(PV_SWEEP[i]), npc[i]


def best_hybrid(sell=SELL, cap_kw=None, seed=SEED):
    lo = np.array([b[1] for b in BOUNDS])
    hi = np.array([b[2] for b in BOUNDS])
    pv0, _ = best_pv(sell, cap_kw)
    obj = lambda x: (evaluate(x[0], x[1], x[2], sell, cap_kw),)
    best, (npc,), n_evals, _, _ = pso.swarm(obj, lo, hi, seed, start=[np.array([pv0, 0, 0])],
                                            **PSO_SIZE)
    return best, npc


def off_grid_optimum():
    runs = pd.read_csv(PSO_CSV)
    return runs[runs["feasible"]].sort_values("npc").iloc[0]


def run_all():
    rows = []
    for sell in SELL_PRICES:
        for m in CAP_MULTIPLES:
            cap = export_cap_kw(m)
            pv, npc_pv = best_pv(sell, cap)
            rows.append(dict(sell=sell, cap_multiple=m, case="grid + PV", pv_kw=pv,
                             batt_strings=0, converter_kw=0.0, npc=npc_pv))
            if m == 1.0:                         # PSO only at the base cap
                x, npc_h = best_hybrid(sell, cap)
                rows.append(dict(sell=sell, cap_multiple=m, case="grid + PV + battery",
                                 pv_kw=x[0], batt_strings=int(x[1]), converter_kw=x[2],
                                 npc=npc_h))
            print(f"  sell {sell:4.2f}  cap {m:.1f}x peak  grid + PV: {pv:6,.0f} kW"
                  f"  NPC ₹{npc_pv/1e6:6.1f} M"
                  + (f"   + battery: {int(x[1])} strings, ₹{npc_h/1e6:6.1f} M" if m == 1.0 else ""))
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    return df


# ---------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------

def verify():
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}   {detail}")

    rel = lambda a, b: abs(a - b) / max(abs(b), 1e-9)
    d = load_inputs()
    print("Grid-connected verification")
    g = evaluate(0, 0, 0, full=True)
    hand = d["load"].sum() * BUY * ANNUITY
    check("grid only = demand x tariff x annuity", rel(g["npc"], hand) < 1e-12,
          f"₹{g['npc']/1e6:.1f} M")
    for pv, nb, conv, sell in [(3000, 0, 0, SELL), (6000, 100, 800, 0.0), (6000, 100, 800, SELL)]:
        r = evaluate(pv, nb, conv, sell, full=True)["res"]
        pv_bal = r["direct"] + r["into"] + r["exp"] + r["curtailed"]
        load_bal = r["direct"] + r["out"] + r["imp"]
        check(f"energy balances close  ({pv} kW, {nb} strings, sell {sell})",
              np.allclose(pv_bal, r["pv"]) and np.allclose(load_bal, r["load"])
              and r["curtailed"].min() > -1e-9,
              f"exported {r['exp'].sum()/1e3:,.0f} MWh, imported {r['imp'].sum()/1e3:,.0f} MWh")
        check("  export never exceeds the cap", r["exp"].max() <= export_cap_kw() + 1e-9)
    loop = run_grid(3000, 1, 0.0)                # battery with no converter = no battery
    vec = run_grid(3000, 0, 0.0)
    check("a battery with no converter changes no flows",
          np.allclose(loop["imp"], vec["imp"]) and np.allclose(loop["exp"], vec["exp"]))
    print("\n  " + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED"))
    return ok


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


def base_cases(df):
    off = off_grid_optimum()
    base = df[(df.sell == SELL) & (df.cap_multiple == 1.0)]
    pv = base[base.case == "grid + PV"].iloc[0]
    hy = base[base.case == "grid + PV + battery"].iloc[0]
    served = load_inputs()["load"].sum()
    off_lcoe = off.npc * crf(R, YEARS) / (served * (1 - off.lpsp))
    return [("Off-grid\nPV + battery", off.npc, off_lcoe,
             f"{off.pv_kw:,.0f} kW PV, {off.batt_kwh/1000:.1f} MWh"),
            ("Grid only", evaluate(0, 0, 0), None, "nothing built"),
            ("Grid + PV", pv.npc, None, f"{pv.pv_kw:,.0f} kW PV"),
            ("Grid + PV\n+ battery", hy.npc, None,
             f"{hy.pv_kw:,.0f} kW PV, {int(hy.batt_strings) * BATT_KWH_PER_STRING:,.0f} kWh")]


def fig_scenarios(df):
    cases = base_cases(df)
    served = load_inputs()["load"].sum()
    fig, ax = plt.subplots(figsize=(9, 4.4))
    colors = [BATT, MUTE, FLOW, FLOW]
    for i, ((name, npc, lcoe, desc), c) in enumerate(zip(cases, colors)):
        lcoe = lcoe if lcoe is not None else npc * crf(R, YEARS) / served
        ax.bar(i, npc / 1e6, color=c, width=0.6)
        ax.text(i, npc / 1e6 + 8, f"₹{npc/1e6:.0f} M\n₹{lcoe:.2f}/kWh", ha="center",
                va="bottom", fontsize=9, color=INK)
        ax.text(i, -32, desc, ha="center", va="top", fontsize=8, color=SLATE)
    ax.axhline(0, color=INK, lw=0.8)
    ax.set_xticks(range(len(cases)))
    ax.set_xticklabels([c[0] for c in cases])
    ax.tick_params(axis="x", pad=26)
    ax.set_ylim(min(0, min(c[1] for c in cases) / 1e6) - 10,
                max(c[1] for c in cases) / 1e6 * 1.25)
    ax.set_ylabel("Net present cost, 15 years (₹ million)")
    title(ax, f"Four ways to supply the same demand  ·  grid at ₹{BUY}/kWh,"
              f" export at ₹{SELL}/kWh up to {export_cap_kw():,.0f} kW")
    style(ax)
    save(fig, "grid_scenarios.png")


def fig_feedin(df):
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 4.2))
    for m, alpha in zip(CAP_MULTIPLES, [0.45, 1.0, 0.7]):
        s = df[(df.case == "grid + PV") & (df.cap_multiple == m)].sort_values("sell")
        ls = "-" if m == 1.0 else "--"
        a1.plot(s.sell, s.pv_kw / 1000, color=FLOW, alpha=alpha, lw=2, ls=ls, marker="o", ms=4)
        a1.text(s.sell.iloc[-1] + 0.1, s.pv_kw.iloc[-1] / 1000, f"cap {m:g}× peak",
                va="center", fontsize=8.5, color=SLATE)
        a2.plot(s.sell, s.npc / 1e6, color=FLOW, alpha=alpha, lw=2, ls=ls, marker="o", ms=4)
        a2.text(s.sell.iloc[-1] + 0.1, s.npc.iloc[-1] / 1e6, f"cap {m:g}× peak",
                va="center", fontsize=8.5, color=SLATE)
    grid_only = evaluate(0, 0, 0) / 1e6
    a2.axhline(grid_only, color=MUTE, ls=":", lw=1.3)
    a2.text(0.05, grid_only + 4, "grid only", fontsize=8.5, color=SLATE)
    for a in (a1, a2):
        a.set_xlabel("Export price (₹/kWh)")
        a.set_xlim(-0.2, SELL + 1.3)
        style(a)
    a1.set_ylabel("Optimal PV (MW)")
    a2.set_ylabel("Net present cost (₹ million)")
    title(a1, "How much PV to build on the grid")
    title(a2, "What it costs  ·  grid + PV")
    save(fig, "grid_feedin.png")


def fig_battery(df):
    strings = np.arange(0, 201, 10)
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    for sell, ls in [(SELL, "-"), (0.0, "--")]:
        pv, _ = best_pv(sell)
        npc = [evaluate(pv, nb, max(100.0, nb * BATT_DISCHARGE_KW_PER_STRING), sell) / 1e6
               for nb in strings]
        mwh = strings * BATT_KWH_PER_STRING / 1000
        ax.plot(mwh, npc, color=BATT, lw=2, ls=ls, marker="o", ms=3.5)
        ax.text(mwh[-1] + 0.2, npc[-1], f"export at ₹{sell:g}/kWh\n({pv:,.0f} kW PV)",
                va="center", fontsize=8.5, color=SLATE)
    ax.set_xlim(-0.3, strings[-1] * BATT_KWH_PER_STRING / 1000 + 3.2)
    ax.set_xlabel("Battery added (MWh)")
    ax.set_ylabel("Net present cost (₹ million)")
    title(ax, "On the grid, every kWh of lead-acid battery adds cost")
    style(ax)
    save(fig, "grid_battery.png")


def fig_dispatch(df):
    base = df[(df.sell == SELL) & (df.cap_multiple == 1.0) & (df.case == "grid + PV")].iloc[0]
    r = run_grid(base.pv_kw, 0, 0.0)
    pv_day = r["pv"].reshape(-1, 24).sum(1)
    days = [int(np.argmax(pv_day)), int(np.argmin(pv_day))]
    hrs = np.arange(24)
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2), sharey=True)
    for ax, day, name in zip(axes, days, ["Sunniest day", "Dullest day"]):
        sl = slice(day * 24, day * 24 + 24)
        ax.fill_between(hrs, 0, r["direct"][sl], color=FLOW, alpha=0.85, lw=0, step="mid",
                        label="PV to load")
        ax.fill_between(hrs, r["direct"][sl], r["direct"][sl] + r["imp"][sl], color=GRID,
                        alpha=0.75, lw=0, step="mid", label="Imported")
        ax.fill_between(hrs, 0, -r["exp"][sl], color=GRID, alpha=0.35, lw=0, step="mid",
                        label="Exported")
        ax.step(hrs, r["load"][sl], where="mid", color=ENERGY, lw=2, label="Demand")
        ax.axhline(0, color=INK, lw=0.8)
        ax.set_xlabel("Hour of day")
        title(ax, f"{name}  ·  day {day + 1}")
        style(ax)
    axes[0].set_ylabel("Power (kW)  ·  below zero = export")
    axes[0].legend(frameon=False, fontsize=8.5, loc="upper left")
    fig.suptitle(f"Grid + {base.pv_kw:,.0f} kW PV, hour by hour", x=0.01, ha="left",
                 fontsize=11, color=INK)
    save(fig, "grid_dispatch.png")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    if not verify():
        raise SystemExit("fix the grid model first")
    print("\nOptimising each case...")
    df = run_all()
    print("\nFigures")
    fig_scenarios(df)
    fig_feedin(df)
    fig_battery(df)
    fig_dispatch(df)
    for name, npc, lcoe, desc in base_cases(df):
        print(f"  {name.replace(chr(10), ' '):24s} ₹{npc/1e6:7.1f} M   {desc}")
