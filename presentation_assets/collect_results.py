"""
Gather every number quoted in the presentation into one JSON file.

Reads the saved results in results/ and calls the model where a value is not
stored, so each figure on a slide traces back to the project's own code.
Nothing here changes the model or its results.

Run from the project root with the project's Python:
    PYTHONPATH=src venv/bin/python presentation_assets/collect_results.py
"""

import contextlib
import io
import json
import numpy as np
import pandas as pd

import simulator
import multiyear
import grid_connected
import sc_study
import pso
from simulator import simulate, load_inputs, crf
from costs import PV, ECON, BATTERY_LA, sc_module_energy_j, sc_modules_in_series

OUT = "presentation_assets/results.json"


def count_checks(fn):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = fn()
    text = buf.getvalue()
    return dict(passed=text.count("[PASS]"), failed=text.count("[FAIL]"), all_ok=bool(ok))


def main():
    r = {}
    d = load_inputs()
    inp = pd.read_csv("data/inputs.csv")
    load = d["load"]
    r["demand"] = dict(annual_mwh=load.sum() / 1e3, peak_kw=load.max(), mean_kw=load.mean(),
                       load_factor=load.mean() / load.max(),
                       mech_mwh=inp.dept_mechanical.sum() / 1e3,
                       elec_mwh=inp.dept_electronics.sum() / 1e3)
    r["weather"] = dict(ghi_2023_kwh_m2=d["ghi"].sum() / 1e3, tamb_mean=d["tamb"].mean(),
                        tamb_min=d["tamb"].min(), tamb_max=d["tamb"].max())
    r["econ"] = dict(real_discount=ECON["real_discount"], nominal=ECON["nominal_discount"],
                     inflation=ECON["inflation"], years=ECON["project_years"],
                     crf=crf(ECON["real_discount"], ECON["project_years"]),
                     pv_cost=PV["capital_inr_per_kw"], batt_cost_unit=BATTERY_LA["capital_inr_per_unit"],
                     float_life=simulator.BATT_FLOAT_LIFE_YEARS)

    runs = pd.read_csv("results/pso_runs.csv")
    best = runs[runs.feasible].sort_values("npc").iloc[0]
    full = simulate(best.pv_kw, best.batt_strings, best.sc_strings, converter_kw=best.converter_kw, full=True)
    parts = {k: v / 1e6 for k, v in full["cost_parts"].items()}
    r["optimum"] = dict(pv_kw=best.pv_kw, strings=int(best.batt_strings),
                        batt_kwh=int(best.batt_strings) * simulator.BATT_KWH_PER_STRING,
                        converter_kw=best.converter_kw, sc_strings=int(best.sc_strings),
                        npc_m=full["npc"] / 1e6, lcoe=full["lcoe"], lpsp=full["lpsp"],
                        batt_life=full["batt_life_years"], capex_m=full["capex"] / 1e6,
                        pv_gen_mwh=full["pv_generated"] / 1e3, curtailed_mwh=full["curtailed"] / 1e3,
                        unmet_mwh=full["unmet"] / 1e3, cost_parts_m=parts,
                        replacements=full["replacements"])
    feas = runs[runs.feasible]
    r["pso"] = dict(runs=len(runs), feasible=len(feas), npc_min=feas.npc.min() / 1e6,
                    npc_max=feas.npc.max() / 1e6,
                    spread_pct=(feas.npc.max() - feas.npc.min()) / feas.npc.min() * 100,
                    evals_per_run=int(runs.evaluations.median()),
                    particles=pso.N_PARTICLES, iterations=pso.N_ITERATIONS,
                    w=pso.INERTIA, c1=pso.C_COGNITIVE, c2=pso.C_SOCIAL,
                    bounds={b[0]: [b[1], b[2]] for b in pso.BOUNDS})
    g = pd.read_csv("results/grid_sweep.csv")
    gf = g[g.lpsp <= simulator.LPSP_TARGET].sort_values("npc").iloc[0]
    r["grid_sweep"] = dict(designs=len(g), npc_m=gf.npc / 1e6, pv_kw=gf.pv_kw,
                           batt_kwh=gf.batt_strings * simulator.BATT_KWH_PER_STRING,
                           converter_kw=gf.converter_kw)

    with contextlib.redirect_stdout(io.StringIO()):
        pass
    r["checks"] = dict(simulator=count_checks(simulator.verify),
                       multiyear=count_checks(multiyear.verify),
                       grid=count_checks(grid_connected.verify))

    # CERC-corrected inputs at the optimum design
    saved = (PV["capital_inr_per_kw"], PV["replacement_inr_per_kw"], ECON["real_discount"])
    PV["capital_inr_per_kw"] = PV["replacement_inr_per_kw"] = 53_002.0
    ECON["real_discount"] = 1.1064 / 1.0571 - 1
    cerc = simulate(best.pv_kw, best.batt_strings, best.sc_strings, converter_kw=best.converter_kw)[0]
    PV["capital_inr_per_kw"], PV["replacement_inr_per_kw"], ECON["real_discount"] = saved
    r["cerc"] = dict(npc_m=cerc / 1e6, change_pct=(cerc / full["npc"] - 1) * 100)

    my = pd.read_csv("results/multiyear.csv")
    t = my[my.growth == 0.10].set_index("strategy")
    r["growth"] = dict(once_m=t.loc["build once", "npc"] / 1e6, staged_m=t.loc["staged", "npc"] / 1e6,
                       once_lcoe=t.loc["build once", "lcoe"], staged_lcoe=t.loc["staged", "lcoe"],
                       saving_pct=(1 - t.loc["staged", "npc"] / t.loc["build once", "npc"]) * 100,
                       spread_pct=float(my.seed_spread_pct.max()),
                       by_rate=[dict(growth=gr, once=a / 1e6, staged=b / 1e6) for gr, a, b in
                                zip(my[my.strategy == "build once"].growth,
                                    my[my.strategy == "build once"].npc,
                                    my[my.strategy == "staged"].npc)])

    gc = pd.read_csv("results/grid_connected.csv")
    base = gc[(gc.sell == grid_connected.SELL) & (gc.cap_multiple == 1.0)]
    gp = base[base.case == "grid + PV"].iloc[0]
    gb = base[base.case == "grid + PV + battery"].iloc[0]
    gpf = grid_connected.evaluate(gp.pv_kw, 0, 0, full=True)
    go = grid_connected.evaluate(0, 0, 0, full=True)
    r["grid"] = dict(grid_only_m=go["npc"] / 1e6, grid_only_lcoe=go["lcoe"],
                     pv_kw=gp.pv_kw, grid_pv_m=gp.npc / 1e6, grid_pv_lcoe=gpf["lcoe"],
                     hybrid_m=gb.npc / 1e6, hybrid_strings=int(gb.batt_strings),
                     tariff=grid_connected.BUY, sell=grid_connected.SELL,
                     export_cap_kw=grid_connected.export_cap_kw(),
                     pv_share=gpf["res"]["direct"].sum() / load.sum())

    w = pd.read_csv("results/performance_weather.csv")
    o, rb = w[w.design == "optimum"], w[w.design == "robust"]
    r["weather_years"] = dict(years=[int(y) for y in o.year], lpsp_opt=list(o.lpsp), lpsp_rob=list(rb.lpsp),
                              fails=int((o.lpsp > simulator.LPSP_TARGET + 1e-9).sum()),
                              worst=float(o.lpsp.max()), worst_year=int(o.loc[o.lpsp.idxmax(), "year"]),
                              opt_mean_npc=o.npc.mean() / 1e6, rob_mean_npc=rb.npc.mean() / 1e6,
                              premium_pct=(rb.npc.mean() / o.npc.mean() - 1) * 100,
                              rob_pv=float(rb.pv_kw.iloc[0]), rob_strings=int(rb.batt_strings.iloc[0]),
                              rob_conv=float(rb.converter_kw.iloc[0]),
                              ghi=list(o.ghi_kwh_m2))

    sp = pd.read_csv("results/sens_spider.csv")
    b0 = sp[sp.change == 0].npc.mean()
    r["spider"] = {p: {f"{c:+.2f}": (v / b0 - 1) * 100 for c, v in zip(s.change, s.npc)}
                   for p, s in sp.groupby("parameter")}
    rel = pd.read_csv("results/sens_reliability.csv")
    rb1 = rel[np.isclose(rel.target, 0.01)].npc.iloc[0]
    r["reliability"] = {f"{t:.4f}": dict(npc_m=n / 1e6, pct=(n / rb1 - 1) * 100)
                        for t, n in zip(rel.target, rel.npc)}
    mc = pd.read_csv("results/montecarlo.csv")
    r["montecarlo"] = dict(n=len(mc), p5=np.percentile(mc.npc, 5) / 1e6, p50=np.percentile(mc.npc, 50) / 1e6,
                           p95=np.percentile(mc.npc, 95) / 1e6,
                           miss_pct=(mc.lpsp > simulator.LPSP_TARGET + 1e-9).mean() * 100)
    tor = pd.read_csv("results/sensitivity.csv")
    r["tornado"] = [dict(parameter=a, low=b, high=c, npc_low=x / 1e6, npc_high=y / 1e6)
                    for a, b, c, x, y in zip(tor.parameter, tor.low, tor.high, tor.npc_low, tor.npc_high)]

    # supercapacitor: transient, C-rate, and the payback at the 1 s and 2 s filters
    spec = pd.read_csv("data/transient_spec.csv")
    step_kw = spec.scaled_kw.sum()
    r["sc"] = dict(step_kw=step_kw, energy_kj=simulator.TRANSIENT_J / 1e3,
                   c_rate=step_kw / r["optimum"]["batt_kwh"],
                   module_j=sc_module_energy_j(), series=sc_modules_in_series(),
                   strings_needed=int(pso.SC_NEEDED),
                   price_placeholder=simulator.SC_PRICE_PER_MODULE_PLACEHOLDER)
    wins, _ = sc_study.windows()
    sizing = pd.read_csv("results/sc_sizing.csv").groupby("tau_s").median(numeric_only=True)
    n_win = sc_study.switching_windows_per_year()

    class Opt:                                  # sc_saving expects a row with these fields
        pv_kw, batt_strings, converter_kw = best.pv_kw, int(best.batt_strings), best.converter_kw
    pay = {}
    for tau in (1, 2, 10):
        saved_inr, lives = sc_study.sc_saving(Opt, Opt.batt_strings, tau, wins, n_win)
        pay[str(tau)] = dict(cost_m=sizing.loc[tau, "cost_inr"] / 1e6, saved_hi_m=saved_inr[0] / 1e6,
                             saved_lo_m=saved_inr[1] / 1e6, strings=int(sizing.loc[tau, "strings"]),
                             ramp_pct=sizing.loc[tau, "batt_ramp_pct"],
                             life_without=lives[0][0], life_with=lives[0][1])
    r["sc"]["payback"] = pay
    r["sc"]["windows_per_year"] = n_win

    with open(OUT, "w") as f:
        json.dump(r, f, indent=1, default=float)
    print(json.dumps({k: r[k] for k in ("optimum", "grid_sweep", "checks", "cerc", "growth", "grid",
                                         "montecarlo", "sc")}, indent=1, default=float)[:4000])


if __name__ == "__main__":
    main()
