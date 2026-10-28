"""
Step 8 - Load growth over the project life.

Kumar et al. assume demand grows 10 % a year, so by year 15 it is 3.8 times
year 1. A design sized for year 1 then falls short within a few years, and
the single-year optimum is not the project's optimum. This script runs all
15 years and compares three ways to deal with growth:

  ignore      the single-year optimum, left unchanged - how fast it fails
  build once  one design installed in year 1 that meets the LPSP target in
              every year, so it is sized for year 15
  staged      capacity added at the start of years 1, 6 and 11, each stage
              sized for its own five years

Battery wear is tracked year by year. Strings bought at different times age
separately: each batch is replaced when its rainflow damage reaches 1 or at
its float life, whichever comes first. PV and converters are replaced when
their fixed lives run out, and every unit left at the end earns salvage for
the life it has left.

With zero growth and one stage the result equals simulator.simulate()
exactly; the verification suite checks this.

Outputs
    results/multiyear.csv        best plan and cost per strategy and growth rate
    figures/growth_lpsp.png      the single-year design failing as demand grows
    figures/growth_npc.png       NPC of each strategy against growth rate
    figures/growth_capacity.png  installed PV and battery, year by year
    figures/growth_spending.png  when the money is spent, staged vs build once

Run from the project root, after pso.py:
    python src/multiyear.py
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from costs import PV, BATTERY_LA, CONVERTER, SUPERCAP, ECON, sc_modules_in_series
from simulator import (run_dispatch, load_inputs, cycle_damage, simulate,
                       LPSP_TARGET, PENALTY, TRANSIENT_J, BATT_KWH_PER_STRING,
                       SC_PRICE_PER_MODULE_PLACEHOLDER, sc_strings_for_energy)
import simulator
import pso
from plot_load import style, INK, SLATE, MUTE, FLOW

PSO_CSV = "results/pso_runs.csv"
OUT_CSV = "results/multiyear.csv"
OUT = "figures"

# =====================================================================
# CONFIG
# =====================================================================

GROWTH = ECON["load_growth_per_year"]          # 10 %, Kumar et al.
GROWTH_RATES = [0.0, 0.025, 0.05, 0.075, 0.10]
STAGE_STARTS = [1, 6, 11]                      # project years a stage is built
SC_STRINGS = sc_strings_for_energy(TRANSIENT_J)

# PSO effort. The staged plan has 9 variables, so it gets a bigger swarm.
ONCE_PSO = dict(n_particles=20, n_iterations=40)
STAGED_PSO = dict(n_particles=30, n_iterations=60)
SEED = 1

BATT = "#2a78d6"
UNMET = "#e34948"
STAGED = "#1baf7a"        # strategy colours: staged accent, build once neutral
ONCE = INK

YEARS = ECON["project_years"]
R = ECON["real_discount"]

# =====================================================================


_YEAR = {}


def run_year(pv_kw, n_strings, conv_kw, factor):
    """One year of dispatch with demand scaled by factor. Memoised."""
    key = (pv_kw, n_strings, conv_kw, round(factor, 9))
    if key not in _YEAR:
        d = load_inputs()
        res = run_dispatch(pv_kw, n_strings, conv_kw, dict(d, load=d["load"] * factor))
        damage = cycle_damage(res["soc_series"] / res["e_batt"]) if n_strings > 0 else 0.0
        _YEAR[key] = dict(lpsp=res["lpsp"], served=res["served"], unmet=res["unmet"],
                          demand=res["demand"], curtailed=res["curtailed"],
                          pv_generated=res["pv_generated"], damage=damage)
    return _YEAR[key]


def installed(stages, starts):
    """Cumulative (PV kW, battery strings, converter kW) in each project year."""
    caps = []
    for y in range(1, YEARS + 1):
        built = [s for s, start in zip(stages, starts) if start <= y]
        caps.append(tuple(float(sum(v)) for v in zip(*built)) if built else (0.0, 0.0, 0.0))
    return caps


def fixed_life_cost(cost, t0, life, spend):
    """
    Present value of replacements, and the salvage value at the project's
    end, for equipment bought at time t0 with a fixed life. Replacements
    are also booked into the yearly spend array.
    """
    replace, last = 0.0, t0
    while last + life < YEARS:
        last += life
        replace += cost / (1.0 + R) ** last
        spend[int(np.ceil(last))] += cost / (1.0 + R) ** last
    salvage = cost * (last + life - YEARS) / life
    return replace, salvage


def evaluate_plan(stages, starts, growth, full=False):
    """
    Cost and reliability of a build plan over the whole project.
    stages: capacity ADDED at each start year, as (PV kW, strings, converter kW).
    Returns (score, NPC, worst-year LPSP), or a full result dict.
    """
    stages = [(max(0.0, p), max(0, int(round(n))), max(0.0, c)) for p, n, c in stages]
    caps = installed(stages, starts)
    factor = [(1.0 + growth) ** (y - 1) for y in range(1, YEARS + 1)]

    # Reliability is worst in the last year of each stage, so test those first
    ends = [s - 1 for s in starts[1:]] + [YEARS]
    viol = sum(max(0.0, run_year(*caps[e - 1], factor[e - 1])["lpsp"] - LPSP_TARGET)
               for e in ends)
    if viol > 0.0 and not full:
        return PENALTY * (1.0 + viol), np.nan, np.nan

    yrs = [run_year(*caps[y - 1], factor[y - 1]) for y in range(1, YEARS + 1)]
    viol = sum(max(0.0, yr["lpsp"] - LPSP_TARGET) for yr in yrs)

    disc = lambda t: (1.0 + R) ** -t
    unit = BATTERY_LA["string_size"]
    sc_price = SUPERCAP["capital_inr_per_module"] or SC_PRICE_PER_MODULE_PLACEHOLDER
    sc_cost = SC_STRINGS * sc_modules_in_series() * sc_price
    parts = dict(pv_capital=0.0, battery_capital=0.0, converter_capital=0.0,
                 sc_capital=sc_cost, battery_replacements=0.0, other_replacements=0.0,
                 om=0.0, salvage=0.0)
    spend = np.zeros(YEARS + 1)            # present value spent in each year, 0 = today
    salvage = 0.0

    for (p, n, c), start in zip(stages, starts):
        t0 = start - 1
        for key, cost, life in [("pv_capital", p * PV["capital_inr_per_kw"], PV["lifetime_years"]),
                                ("converter_capital", c * CONVERTER["capital_inr_per_kw"],
                                 CONVERTER["lifetime_years"])]:
            parts[key] += cost * disc(t0)
            spend[t0] += cost * disc(t0)
            rep, salv = fixed_life_cost(cost, t0, life, spend)
            parts["other_replacements"] += rep
            salvage += salv
        parts["battery_capital"] += n * unit * BATTERY_LA["capital_inr_per_unit"] * disc(t0)
        spend[t0] += n * unit * BATTERY_LA["capital_inr_per_unit"] * disc(t0)
    spend[0] += sc_cost
    salvage += sc_cost * (SUPERCAP["lifetime_years"] - YEARS) / SUPERCAP["lifetime_years"]

    # battery batches: [strings, damage, age in years]
    batches = []
    float_life = simulator.BATT_FLOAT_LIFE_YEARS
    batt_unit = unit * BATTERY_LA["replacement_inr_per_unit"]
    for y in range(1, YEARS + 1):
        batches += [[n, 0.0, 0.0] for (_, n, _), s in zip(stages, starts) if s == y and n > 0]
        d = yrs[y - 1]["damage"]
        for b in batches:
            t = 0.0                                    # time used so far this year
            while True:
                left = 1.0 - t
                to_end = min((1.0 - b[1]) / d if d > 0 else np.inf, float_life - b[2])
                if to_end < left - 1e-9:               # dies within this year
                    when = y - 1 + t + to_end
                    parts["battery_replacements"] += b[0] * batt_unit * disc(when)
                    spend[int(np.ceil(when))] += b[0] * batt_unit * disc(when)
                    b[1], b[2] = 0.0, 0.0
                    t += to_end
                else:
                    b[1] += d * left
                    b[2] += left
                    break

        pv_c, nb_c, conv_c = caps[y - 1]
        om = (pv_c * PV["om_inr_per_kw_year"]
              + nb_c * unit * BATTERY_LA["om_inr_per_unit_year"]
              + conv_c * CONVERTER["om_inr_per_kw_year"]
              + ECON["system_fixed_om_per_year"])
        parts["om"] += om * disc(y)
        spend[y] += om * disc(y)

    for n, dmg, age in batches:
        salvage += n * batt_unit * (1.0 - max(dmg, age / float_life))
    parts["salvage"] = -salvage * disc(YEARS)
    spend[YEARS] -= salvage * disc(YEARS)

    npc = sum(parts.values())
    worst = max(yr["lpsp"] for yr in yrs)
    score = npc if viol == 0.0 else PENALTY * (1.0 + viol)
    if not full:
        return score, npc, worst

    served_pv = sum(yr["served"] * disc(y) for y, yr in zip(range(1, YEARS + 1), yrs))
    return dict(score=score, npc=npc, worst_lpsp=worst, parts=parts, stages=stages,
                caps=caps, years=yrs, factor=factor, spend=spend,
                lcoe=npc / served_pv, feasible=viol == 0.0)


# ---------------------------------------------------------------------
# Optimisation
# ---------------------------------------------------------------------

def single_year_optimum():
    runs = pd.read_csv(PSO_CSV)
    best = runs[runs["feasible"]].sort_values("npc").iloc[0]
    return float(best.pv_kw), int(best.batt_strings), float(best.converter_kw)


def upper_bounds(growth):
    """Generous bounds: 2.5 times the single-year optimum, grown to year 15."""
    base = np.array(single_year_optimum())
    return 2.5 * base * (1.0 + growth) ** (YEARS - 1)


def optimise_once(growth, seed=SEED):
    hi = upper_bounds(growth)
    lo = np.zeros(3)
    obj = lambda x: evaluate_plan([x], [1], growth)
    best, (score, npc, worst), n_evals, _, _ = pso.swarm(obj, lo, hi, seed, **ONCE_PSO)
    return [tuple(best)], score, n_evals


def optimise_staged(growth, once_plan, seed=SEED):
    hi = np.tile(upper_bounds(growth), 3)
    lo = np.zeros(9)
    base = np.array(single_year_optimum())
    f = lambda y: (1.0 + growth) ** (y - 1)
    # warm starts: the build-once plan (so staged can only improve on it),
    # and a plan that scales the single-year design to each stage's last year
    scaled = [base * f(5), base * (f(10) - f(5)), base * (f(15) - f(10))]
    start = [np.concatenate([np.array(once_plan[0]), np.zeros(6)]), np.concatenate(scaled)]
    obj = lambda x: evaluate_plan([x[0:3], x[3:6], x[6:9]], STAGE_STARTS, growth)
    best, (score, npc, worst), n_evals, _, _ = pso.swarm(obj, lo, hi, seed, start=start,
                                                         **STAGED_PSO)
    return [tuple(best[0:3]), tuple(best[3:6]), tuple(best[6:9])], score, n_evals


def run_all():
    rows = []
    for g in GROWTH_RATES:
        once, s1, e1 = optimise_once(g)
        staged, s2, e2 = optimise_staged(g, once)
        for name, plan, starts, score, ev in [("build once", once, [1], s1, e1),
                                              ("staged", staged, STAGE_STARTS, s2, e2)]:
            r = evaluate_plan(plan, starts, g, full=True)
            row = dict(growth=g, strategy=name, npc=r["npc"], lcoe=r["lcoe"],
                       worst_lpsp=r["worst_lpsp"], feasible=r["feasible"], evaluations=ev)
            for k, (p, n, c) in enumerate(r["stages"]):
                row.update({f"pv_kw_{k+1}": p, f"batt_strings_{k+1}": n, f"converter_kw_{k+1}": c})
            rows.append(row)
            print(f"  growth {g:5.1%}  {name:10s}  NPC ₹{r['npc']/1e6:7.1f} M"
                  f"  LCOE {r['lcoe']:5.2f}  worst LPSP {r['worst_lpsp']:.3%}"
                  f"  ({ev} evaluations)")
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False)
    return df


def plan_from_row(row):
    k = 3 if row.strategy == "staged" else 1
    stages = [(row[f"pv_kw_{i}"], row[f"batt_strings_{i}"], row[f"converter_kw_{i}"])
              for i in range(1, k + 1)]
    return stages, (STAGE_STARTS if k == 3 else [1])


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
    print("Multi-year verification")
    for pv, nb, conv in [single_year_optimum(), (5000.0, 500, 1500.0), (3000.0, 60, 800.0)]:
        one = simulate(pv, nb, SC_STRINGS, converter_kw=conv, full=True)
        multi = evaluate_plan([(pv, nb, conv)], [1], 0.0, full=True)
        check(f"no growth = single-year model  ({pv:,.0f} kW, {nb} strings)",
              rel(multi["npc"], one["npc"]) < 1e-9 and rel(multi["worst_lpsp"], one["lpsp"]) < 1e-9,
              f"NPC {multi['npc']/1e6:.3f} vs {one['npc']/1e6:.3f} M, "
              f"battery life {one['batt_life_years']:.2f} y")
    p = single_year_optimum()
    split = evaluate_plan([p, (0, 0, 0), (0, 0, 0)], STAGE_STARTS, 0.0, full=True)
    check("empty later stages change nothing",
          rel(split["npc"], evaluate_plan([p], [1], 0.0)[1]) < 1e-12)
    grown = evaluate_plan([p], [1], GROWTH, full=True)
    lp = [y["lpsp"] for y in grown["years"]]
    check("with growth, a fixed design gets less reliable every year",
          all(b >= a - 1e-12 for a, b in zip(lp, lp[1:])),
          f"LPSP {lp[0]:.2%} in year 1 -> {lp[-1]:.1%} in year 15")
    check("cost parts add up to the NPC",
          rel(sum(grown["parts"].values()), grown["npc"]) < 1e-12)
    check("yearly spending adds up to the NPC",
          rel(grown["spend"].sum(), grown["npc"]) < 1e-12)
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


def fig_lpsp():
    p = single_year_optimum()
    yrs = np.arange(1, YEARS + 1)
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    for g, alpha in [(0.025, 0.45), (0.05, 0.7), (0.10, 1.0)]:
        r = evaluate_plan([p], [1], g, full=True)
        lp = np.array([y["lpsp"] for y in r["years"]]) * 100
        ax.plot(yrs, lp, color=UNMET, alpha=alpha, lw=2, marker="o", ms=4)
        ax.text(yrs[-1] + 0.2, lp[-1], f"{g:.1%} a year", va="center", fontsize=9, color=SLATE)
        fail = np.argmax(lp > LPSP_TARGET * 100) if (lp > LPSP_TARGET * 100).any() else None
        if g == 0.10 and fail is not None:
            ax.annotate(f"10 % growth: fails\nfrom year {yrs[fail]}", (yrs[fail], lp[fail]),
                        xytext=(yrs[fail] - 0.6, lp[fail] + 14), fontsize=9, color=INK,
                        arrowprops=dict(arrowstyle="-", color=MUTE, lw=0.8))
    ax.axhline(LPSP_TARGET * 100, color=INK, ls="--", lw=1.2)
    ax.text(YEARS + 0.2, LPSP_TARGET * 100 + 0.8, "1 % target", va="bottom", fontsize=9, color=SLATE)
    ax.set_xlim(0.5, YEARS + 2.5)
    ax.set_xticks(yrs)
    ax.set_xlabel("Project year")
    ax.set_ylabel("Unmet demand, LPSP (%)")
    title(ax, f"The single-year optimum ({p[0]:,.0f} kW, {p[1] * BATT_KWH_PER_STRING / 1000:.1f} MWh)"
              " as demand grows")
    style(ax)
    save(fig, "growth_lpsp.png")


def fig_npc(df):
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    for name, c, ls in [("build once", ONCE, "--"), ("staged", STAGED, "-")]:
        s = df[df.strategy == name].sort_values("growth")
        ax.plot(s.growth * 100, s.npc / 1e6, color=c, lw=2, ls=ls, marker="o", ms=5)
        ax.text(s.growth.iloc[-1] * 100 + 0.15, s.npc.iloc[-1] / 1e6, name.capitalize(),
                va="center", fontsize=9, color=SLATE)
    s1 = df[(df.strategy == "build once") & (df.growth == GROWTH)].npc.iloc[0] / 1e6
    s2 = df[(df.strategy == "staged") & (df.growth == GROWTH)].npc.iloc[0] / 1e6
    x = GROWTH * 100 + 1.6
    ax.annotate("", (x, s2), xytext=(x, s1),
                arrowprops=dict(arrowstyle="<->", color=MUTE, lw=1))
    ax.text(x + 0.2, (s1 + s2) / 2, f"staging\nsaves\n₹{s1 - s2:.0f} M\n({(s1 - s2)/s1:.0%})",
            fontsize=9, color=INK, va="center")
    ax.set_xlim(-0.4, GROWTH * 100 + 3.4)
    ax.set_xticks(np.arange(0, GROWTH * 100 + 0.1, 2.5))
    ax.set_xlabel("Demand growth (% a year)")
    ax.set_ylabel("Net present cost (₹ million)")
    title(ax, "Cost of meeting 1 % LPSP in every one of the 15 years")
    style(ax)
    save(fig, "growth_npc.png")


def fig_capacity(df, growth=GROWTH):
    yrs = np.arange(1, YEARS + 1)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 4.2))
    demand = None
    for name, ls in [("build once", "--"), ("staged", "-")]:
        row = df[(df.strategy == name) & (df.growth == growth)].iloc[0]
        r = evaluate_plan(*plan_from_row(row), growth, full=True)
        caps = np.array(r["caps"])
        demand = np.array([y["demand"] for y in r["years"]])
        for ax, v, c in [(a1, caps[:, 0] / 1000, FLOW),
                         (a2, caps[:, 1] * BATT_KWH_PER_STRING / 1000, BATT)]:
            ax.step(np.append(yrs, YEARS + 1) - 0.5, np.append(v, v[-1]), where="post",
                    color=c, lw=2, ls=ls)
            ax.text(YEARS + 0.7, v[-1], name, va="center", fontsize=9, color=SLATE)
    a1.set_ylabel("Installed PV (MW)")
    a2.set_ylabel("Installed battery (MWh)")
    title(a1, f"PV  ·  demand grows {growth:.0%} a year, {demand[-1]/demand[0]:.1f}× by year 15")
    title(a2, "Battery")
    for ax in (a1, a2):
        ax.set_xlim(0.5, YEARS + 3.5)
        ax.set_ylim(0, None)
        ax.set_xticks(yrs)
        ax.set_xlabel("Project year")
        style(ax)
    save(fig, "growth_capacity.png")


def fig_spending(df, growth=GROWTH):
    yrs = np.arange(0, YEARS + 1)
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    for name, c, ls in [("build once", ONCE, "--"), ("staged", STAGED, "-")]:
        row = df[(df.strategy == name) & (df.growth == growth)].iloc[0]
        r = evaluate_plan(*plan_from_row(row), growth, full=True)
        cum = np.cumsum(r["spend"]) / 1e6
        ax.step(yrs, cum, where="post", color=c, lw=2, ls=ls)
        ax.text(YEARS + 0.2, cum[-1], f"{name}  ₹{cum[-1]:.0f} M", va="center",
                fontsize=9, color=SLATE)
    ax.set_xlim(0, YEARS + 3.5)
    ax.set_xticks(yrs)
    ax.set_xlabel("Project year")
    ax.set_ylabel("Cumulative spending, present value (₹ million)")
    title(ax, f"When the money is spent  ·  {growth:.0%} growth  ·  final value = NPC")
    style(ax)
    save(fig, "growth_spending.png")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    if not verify():
        raise SystemExit("fix the multi-year model before optimising")
    print("\nOptimising each strategy at each growth rate...")
    df = run_all()
    print("\nFigures")
    fig_lpsp()
    fig_npc(df)
    fig_capacity(df)
    fig_spending(df)
