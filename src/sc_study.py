"""
Supercapacitor study - when does a battery-supercapacitor hybrid pay?

The hourly model cannot see a supercapacitor, so in it the SC is pure
cost. This script asks the question the thesis needs answered instead of
assuming the answer:

  A. What does the SC actually see?  A one-second prototype of the
     workshop's switching load, built from the same equipment list as
     prepare_data.py, with motor starting surges added.
  B. How big must the SC be?  The storage power is split by a first-order
     low-pass filter: slow changes to the battery, fast ones to the SC.
     The filter time constant tau sets the SC size and cost.
  C. When is it worth it?  The battery-life extension the SC must buy to
     repay its cost, and the battery size below which the transient is a
     real stress on the battery.

Every SC number still rests on placeholders (module price, starting surge,
on-times). They are declared below so they can be replaced.

Outputs (figures/)
    sc_resolution.png     one switching window at 1 s, 1 min and 1 h
    sc_power_split.png    battery and SC shares of the storage power
    sc_sizing.png         SC modules and cost against filter time constant
    sc_battery_relief.png battery peak power and ramp rate against tau
    sc_crate.png          the transient as a C-rate, against battery size
    sc_breakeven.png      battery-life extension the SC must buy to pay off

Run from the project root, after pso.py:
    python src/sc_study.py
"""

import math
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from prepare_data import DEPARTMENTS, SUBSET
from costs import SUPERCAP, CONVERTER, sc_module_energy_j, sc_modules_in_series
from simulator import (compute_npc, simulate, load_inputs, TRANSIENT_J,
                       SC_PRICE_PER_MODULE_PLACEHOLDER, BATT_KWH_PER_STRING)
from plot_load import style, INK, SLATE, MUTE, ENERGY, FLOW

OUT = "figures"
PSO_CSV = "results/pso_runs.csv"
SC_CSV = "results/sc_sizing.csv"

# =====================================================================
# CONFIG - placeholders, replace with measurements or datasheets
# =====================================================================

WINDOW_S = 1800                 # length of one switching window, seconds
N_WINDOWS = 30                  # random windows averaged for the sizing curves
WINDOW_HOUR = 11                # a weekday working hour
RANDOM_SEED = 7

IN_USE_PROB = 0.65              # same as the binomial in prepare_data.py

# mean time a machine stays on once switched on, seconds
MEAN_ON_S = {"SMAW welding set": 25, "TIG/MAG welding set": 40,
             "CNC lathe": 240, "CNC vertical milling": 300,
             "Wire-cut EDM": 900, "Die-sinking EDM": 600,
             "Foundry melting furnace": 900, "Conventional lathe/mill": 120,
             "Compressor (shop air)": 180, "Motor-generator set": 300,
             "Power electronics test bench": 120, "High-voltage test set": 60,
             "Programmable DC load/source": 90}
DEFAULT_ON_S = 120

# Direct-on-line motors draw a starting surge. CNC spindles run on
# drives and soft-start, so they are excluded.
DOL_MOTORS = {"Conventional lathe/mill", "Compressor (shop air)", "Motor-generator set"}
INRUSH_MULTIPLE = 5.0           # starting power / rated power, at t = 0
INRUSH_DECAY_S = 0.7            # time constant of the surge
WELD_FLICKER = 0.25             # +/- fraction, second to second, while arcing

TAUS_S = [1, 2, 5, 10, 20, 30, 60, 120, 300]
DEMO_TAU_S = 10

DCDC_INR_PER_KW = CONVERTER["capital_inr_per_kw"]   # SC needs its own DC-DC stage

# Palette shared with plot_load.py / plot_results.py
BATT = "#2a78d6"
SC = "#6250d6"

# =====================================================================


def transient_units():
    """Every switching machine unit in the studied departments."""
    units = []
    for dept in SUBSET:
        for item in DEPARTMENTS[dept]["equipment"]:
            if item["transient"] and WINDOW_HOUR in item["hours"]:
                units += [item] * item["count"]
    return units


def unit_trace(item, n, rng):
    """One machine's power, kW, second by second, as a two-state Markov chain."""
    p = IN_USE_PROB * item["duty"]
    t_on = MEAN_ON_S.get(item["name"], DEFAULT_ON_S)
    off_to_on = min(1.0, p / (1.0 - p) / t_on)
    on_to_off = 1.0 / t_on

    on = rng.random() < p
    since = 10_000
    out = np.zeros(n)
    for t in range(n):
        if on and rng.random() < on_to_off:
            on = False
        elif not on and rng.random() < off_to_on:
            on, since = True, 0
        if on:
            kw = item["kw"]
            if item["name"] in DOL_MOTORS:
                kw *= 1.0 + (INRUSH_MULTIPLE - 1.0) * math.exp(-since / INRUSH_DECAY_S)
            if "welding" in item["name"]:
                kw *= 1.0 + rng.uniform(-WELD_FLICKER, WELD_FLICKER)
            out[t] = kw
            since += 1
    return out


def storage_window(rng, units, base_kw):
    """
    Power the storage must supply over one window, kW (positive = discharge).
    The hourly average of the switching load is replaced by its second-by-
    second trace, so the window still averages to the hourly value.
    """
    switching = sum(unit_trace(u, WINDOW_S, rng) for u in units)
    mean_switching = sum(IN_USE_PROB * u["duty"] * u["kw"] for u in units)
    return base_kw - mean_switching + switching


def low_pass(x, tau_s):
    """First-order low-pass filter at 1 s steps; returns the battery share."""
    a = 1.0 / (tau_s + 1.0)
    y = np.empty_like(x)
    y[0] = x[:60].mean()            # start settled, not from zero
    for t in range(1, len(x)):
        y[t] = y[t - 1] + a * (x[t] - y[t - 1])
    return y


def sc_requirement(p_sc):
    """Energy swing (J) and peak power (kW) the SC must handle."""
    e = np.cumsum(p_sc) * 1000.0    # kW x 1 s -> J
    return e.max() - e.min(), np.abs(p_sc).max()


def sc_cost(energy_j, power_kw):
    per_string = sc_module_energy_j() * sc_modules_in_series()
    strings = max(1, math.ceil(energy_j / per_string))
    price = SUPERCAP["capital_inr_per_module"] or SC_PRICE_PER_MODULE_PLACEHOLDER
    modules = strings * sc_modules_in_series()
    return strings, modules, modules * price + power_kw * DCDC_INR_PER_KW


def optimum():
    runs = pd.read_csv(PSO_CSV)
    return runs[runs["feasible"]].sort_values("npc").iloc[0]


def save(fig, name):
    fig.tight_layout()
    fig.savefig(f"{OUT}/{name}", dpi=150)
    plt.close(fig)
    print(f"  {name}")


def title(ax, text):
    ax.set_title(text, fontsize=11, loc="left", color=INK)


# ---------------------------------------------------------------------
# A + B: switching windows, power split, SC sizing
# ---------------------------------------------------------------------

def windows():
    d = load_inputs()
    hod = np.arange(d["n"]) % 24
    dow = (np.arange(d["n"]) // 24 + 6) % 7
    # storage supplies the evening: use a working hour's load with no PV, so
    # the window is all battery - the case where the SC matters most
    mask = (hod == WINDOW_HOUR) & (dow < 5)
    base = float(np.median(d["load"][mask]))
    rng = np.random.default_rng(RANDOM_SEED)
    units = transient_units()
    return [storage_window(rng, units, base) for _ in range(N_WINDOWS)], base


def sizing_table(wins):
    rows = []
    for w_i, p in enumerate(wins):
        ramp0 = np.abs(np.diff(p)).max()
        peak0 = p.max() - p.mean()
        for tau in TAUS_S:
            pb = low_pass(p, tau)
            e, pw = sc_requirement(p - pb)
            strings, modules, cost = sc_cost(e, pw)
            rows.append(dict(window=w_i, tau_s=tau, sc_energy_kj=e / 1000,
                             sc_power_kw=pw, strings=strings, modules=modules,
                             cost_inr=cost,
                             batt_ramp_pct=np.abs(np.diff(pb)).max() / ramp0 * 100,
                             batt_peak_pct=(pb.max() - pb.mean()) / peak0 * 100))
    df = pd.DataFrame(rows)
    df.to_csv(SC_CSV, index=False)
    return df


def fig_resolution(p):
    t = np.arange(len(p)) / 60
    minute = p[:len(p) // 60 * 60].reshape(-1, 60).mean(1)
    fig, ax = plt.subplots(figsize=(11, 4))
    ax.plot(t, p, color=INK, lw=0.7, label="1-second (what the SC sees)")
    ax.step(np.arange(len(minute) + 1), np.append(minute, minute[-1]), where="post",
            color=ENERGY, lw=1.8, label="1-minute average (planned model)")
    ax.axhline(p.mean(), color=FLOW, lw=2, ls="--", label="1-hour average (current model)")
    i = int(p.argmax())
    ax.annotate(f"motor starting surge\n{p.max():.0f} kW", (t[i], p.max()),
                xytext=(t[i] + 1.5, p.max() * 0.98), fontsize=8.5, color=SLATE,
                arrowprops=dict(arrowstyle="-", color=MUTE, lw=0.8))
    ax.set_xlabel("Minutes into the window")
    ax.set_ylabel("Storage power (kW)")
    ax.set_xlim(0, len(p) / 60)
    title(ax, "One 30-minute workshop window at three time resolutions  ·  synthetic, from the equipment list")
    ax.legend(frameon=False, fontsize=9, loc="lower right", ncol=3)
    style(ax)
    save(fig, "sc_resolution.png")


def fig_power_split(p):
    pb = low_pass(p, DEMO_TAU_S)
    i0 = max(0, int(p.argmax()) - 120)
    sl = slice(i0, i0 + 300)
    t = np.arange(sl.stop - sl.start)

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 5.6), sharex=True,
                                 gridspec_kw=dict(height_ratios=[1.6, 1]))
    a1.plot(t, p[sl], color=MUTE, lw=1.0, label="Storage power, battery only")
    a1.plot(t, pb[sl], color=BATT, lw=2.2, label=f"Battery share with SC (τ = {DEMO_TAU_S} s)")
    a1.set_ylabel("Power (kW)")
    title(a1, "The low-pass split: the battery sees a smooth curve")
    a1.legend(frameon=False, fontsize=9, loc="upper right")
    style(a1)
    a2.fill_between(t, 0, (p - pb)[sl], color=SC, alpha=0.85, lw=0)
    a2.axhline(0, color=MUTE, lw=0.8)
    a2.set_ylabel("SC power (kW)")
    a2.set_xlabel("Seconds")
    title(a2, "The SC's share: short, sharp, and back to zero")
    style(a2)
    save(fig, "sc_power_split.png")


def band(ax, df, col, color, scale=1.0, label=None):
    g = df.groupby("tau_s")[col]
    med, lo, hi = g.median() * scale, g.quantile(0.1) * scale, g.quantile(0.9) * scale
    ax.fill_between(med.index, lo, hi, color=color, alpha=0.18, lw=0)
    ax.plot(med.index, med, color=color, lw=2, marker="o", ms=5, label=label)
    return med


def fig_sizing(df):
    current = math.ceil(TRANSIENT_J / (sc_module_energy_j() * sc_modules_in_series()))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.2))
    band(a1, df, "strings", SC, label="Median of 30 windows, 10-90 % band")
    a1.axhline(current, color=ENERGY, ls="--", lw=1.3)
    a1.text(TAUS_S[-1], current * 0.82, f"current design: {current} strings (93 kW for 5 s)",
            color=ENERGY, fontsize=8.5, ha="right", va="top")
    a1.set_xscale("log")
    a1.set_yscale("log")
    a1.set_xlabel("Filter time constant τ (s, log)")
    a1.set_ylabel("SC strings needed (log)")
    title(a1, "Smoothing longer needs far more SC")
    a1.legend(frameon=False, fontsize=8.5, loc="upper left")
    style(a1)
    band(a2, df, "cost_inr", SC, scale=1e-6)
    a2.set_xscale("log")
    a2.set_yscale("log")
    a2.set_xlabel("Filter time constant τ (s, log)")
    a2.set_ylabel("SC + DC-DC capital (₹ million, log)")
    title(a2, "...and its cost climbs just as fast")
    style(a2)
    save(fig, "sc_sizing.png")


def fig_relief(df):
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    band(ax, df, "batt_ramp_pct", BATT, label="Fastest battery ramp (kW/s)")
    band(ax, df, "batt_peak_pct", INK, label="Battery peak above its mean")
    ax.axhline(100, color=MUTE, ls=":", lw=1)
    ax.text(TAUS_S[-1], 102, "battery only = 100 %", ha="right", fontsize=8.5, color=SLATE)
    ax.set_xscale("log")
    ax.set_ylim(0, 110)
    ax.set_xlabel("Filter time constant τ (s, log)")
    ax.set_ylabel("% of the battery-only value")
    title(ax, "What the SC takes off the battery")
    ax.legend(frameon=False, fontsize=9, loc="center right")
    style(ax)
    save(fig, "sc_battery_relief.png")


# ---------------------------------------------------------------------
# C: when the hybrid makes sense
# ---------------------------------------------------------------------

def fig_crate(peak_kw, opt):
    kwh = np.logspace(np.log10(50), np.log10(30000), 200)
    fig, ax = plt.subplots(figsize=(8.5, 4.4))
    ax.plot(kwh, 93.0 / kwh, color=ENERGY, lw=2, label="93 kW coincident step")
    ax.plot(kwh, peak_kw / kwh, color=SC, lw=2, label=f"{peak_kw:.0f} kW worst surge (prototype)")
    ax.axhline(0.1, color=MUTE, ls="--", lw=1.2)
    ax.text(kwh[0] * 1.1, 0.115, "C/10: the rate tubular lead-acid capacity is rated at",
            fontsize=8.5, color=SLATE)
    e = opt.batt_kwh
    ax.axvline(e, color=INK, ls=":", lw=1.2)
    ax.text(e * 0.92, 2, f"this design\n{e/1000:.1f} MWh\n{93/e:.3f} C", ha="right",
            fontsize=8.5, color=INK)
    ax.fill_betweenx([0.1, 10], kwh[0], peak_kw / 0.1, color=SC, alpha=0.07, lw=0)
    ax.text(kwh[0] * 1.1, 3, "SC relieves\nreal stress here", fontsize=9, color=SC)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_ylim(1e-3, 10)
    ax.set_xlim(kwh[0], kwh[-1])
    ax.set_xlabel("Battery bank (kWh, log)")
    ax.set_ylabel("Transient as a C-rate (log)")
    title(ax, "The transient only matters to a small battery")
    ax.legend(frameon=False, fontsize=9, loc="lower left")
    style(ax)
    save(fig, "sc_crate.png")


def npc_battery_only(pv, nb, conv, life):
    return compute_npc(pv, nb, 0, conv, life)[0]


def fig_breakeven(opt, sc_package_inr, sc_filter_inr):
    full = simulate(opt.pv_kw, opt.batt_strings, 0, converter_kw=opt.converter_kw, full=True)
    life0 = full["batt_life_years"]
    ext = np.linspace(0, 60, 241)

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 4.4))
    banks = [(opt.batt_strings, f"{opt.batt_kwh/1000:.1f} MWh (this design)", BATT),
             (max(1, round(opt.batt_strings / 4)), None, FLOW),
             (max(1, round(opt.batt_strings / 15)), None, ENERGY)]
    for nb, label, c in banks:
        base = npc_battery_only(opt.pv_kw, nb, opt.converter_kw, life0)
        saving = [(base - npc_battery_only(opt.pv_kw, nb, opt.converter_kw,
                                           life0 * (1 + x / 100))) / 1e6 for x in ext]
        a1.plot(ext, saving, color=c, lw=2,
                label=label or f"{nb * BATT_KWH_PER_STRING / 1000:.1f} MWh bank")
    for cost, name, x, ha in [(sc_package_inr, "4-string SC + 93 kW DC-DC", ext[-1], "right"),
                              (sc_filter_inr, f"SC for τ = {DEMO_TAU_S} s filter", 14, "left")]:
        a1.axhline(cost / 1e6, color=SC, ls="--", lw=1.2)
        a1.text(x, cost / 1e6 * 1.06, f"{name}  ₹{cost/1e6:.1f} M", ha=ha,
                fontsize=8.5, color=SC)
    a1.set_xlabel("Battery life extension (%)")
    a1.set_ylabel("NPC saved (₹ million)")
    title(a1, f"What a longer battery life is worth  ·  base life {life0:.1f} years")
    a1.legend(frameon=False, fontsize=8.5, loc="upper left")
    style(a1)

    strings = np.unique(np.round(np.logspace(0, np.log10(opt.batt_strings * 1.5), 40)).astype(int))
    need = []
    for nb in strings:
        base = npc_battery_only(opt.pv_kw, nb, opt.converter_kw, life0)
        x_req = np.nan
        for x in np.linspace(0, 300, 1201):
            if base - npc_battery_only(opt.pv_kw, nb, opt.converter_kw, life0 * (1 + x / 100)) >= sc_package_inr:
                x_req = x
                break
        need.append(x_req)
    mwh = strings * BATT_KWH_PER_STRING / 1000
    a2.plot(mwh, need, color=SC, lw=2)
    a2.axvline(opt.batt_kwh / 1000, color=INK, ls=":", lw=1.2)
    i = np.argmin(np.abs(strings - opt.batt_strings))
    a2.plot(mwh[i], need[i], "o", color=SC, ms=7)
    a2.text(mwh[i] * 0.93, need[i] + 15, f"this design: {need[i]:.0f} %", ha="right",
            fontsize=9, color=INK)
    a2.set_xscale("log")
    a2.set_ylim(0, 300)
    a2.set_xlabel("Battery bank (MWh, log)")
    a2.set_ylabel("Life extension needed to repay the SC (%)")
    title(a2, "Break-even for the 4-string SC package")
    style(a2)
    save(fig, "sc_breakeven.png")
    return life0, need[i]


def main():
    os.makedirs(OUT, exist_ok=True)
    if not os.path.exists(PSO_CSV):
        raise FileNotFoundError(f"{PSO_CSV} not found - run src/pso.py first")
    opt = optimum()

    print(f"Simulating {N_WINDOWS} one-second switching windows ({WINDOW_S} s each)...")
    wins, base = windows()
    df = sizing_table(wins)
    demo = max(wins, key=lambda w: w.max())
    peak = float(np.median([w.max() - w.mean() for w in wins]))

    fig_resolution(demo)
    fig_power_split(demo)
    fig_sizing(df)
    fig_relief(df)
    fig_crate(peak, opt)

    price = SUPERCAP["capital_inr_per_module"] or SC_PRICE_PER_MODULE_PLACEHOLDER
    n_str = math.ceil(TRANSIENT_J / (sc_module_energy_j() * sc_modules_in_series()))
    package = n_str * sc_modules_in_series() * price + 93.0 * DCDC_INR_PER_KW
    filt = df[df.tau_s == DEMO_TAU_S].cost_inr.median()
    life0, need = fig_breakeven(opt, package, filt)

    med = df.groupby("tau_s").median(numeric_only=True)
    print("\n  tau (s)   SC strings   SC kJ   SC peak kW   cost ₹M   battery ramp %")
    for tau, r in med.iterrows():
        print(f"  {tau:7.0f}   {r.strings:10.0f}   {r.sc_energy_kj:5.0f}   {r.sc_power_kw:10.0f}"
              f"   {r.cost_inr/1e6:7.1f}   {r.batt_ramp_pct:14.0f}")
    print(f"\n  median surge above the window mean: {peak:.0f} kW")
    print(f"  4-string SC + 93 kW DC-DC package: ₹{package/1e6:.1f} M")
    print(f"  battery life {life0:.1f} y; the package pays off if it extends life by {need:.0f} %")


if __name__ == "__main__":
    main()
