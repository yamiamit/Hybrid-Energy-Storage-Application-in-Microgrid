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
  C. Is it worth it?  The battery wear the SC removes, by rainflow counting
     the second-scale cycles with and without it against the datasheet
     cycle-life curve, turned into NPC saved and set against the SC's cost,
     for this design and for smaller battery banks.

Every SC number still rests on placeholders (module price, starting surge,
on-times). They are declared below so they can be replaced.

Outputs (figures/)
    sc_resolution.png     one switching window at 1 s, 1 min and 1 h
    sc_power_split.png    battery and SC shares of the storage power
    sc_sizing.png         SC modules and cost against filter time constant
    sc_battery_relief.png battery peak power and ramp rate against tau
    sc_crate.png          the transient as a C-rate, against battery size
    sc_payback.png        battery NPC the SC saves against what it costs

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

from prepare_data import DEPARTMENTS, SUBSET, VACATION_ACTIVITY, vacation_mask
from costs import SUPERCAP, CONVERTER, sc_module_energy_j, sc_modules_in_series
from simulator import (compute_npc, simulate, load_inputs, TRANSIENT_J,
                       SC_PRICE_PER_MODULE_PLACEHOLDER, BATT_KWH_PER_STRING,
                       BATT_CYCLE_LIFE, BATT_FLOAT_LIFE_YEARS,
                       cycles_to_failure, rainflow_cycles, cycle_damage)
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
PAYBACK_TAU_S = 2               # filter used for the bank-size comparison

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


def switching_windows_per_year():
    """
    Windows a year in which the workshop is switching: weekday hours when
    any transient machine is scheduled, scaled by the vacation activity.
    Every such window is assumed as busy as the 11 am one - generous to the SC.
    """
    hours = sorted({h for dept in SUBSET for item in DEPARTMENTS[dept]["equipment"]
                    if item["transient"] for h in item["hours"]})
    t = pd.date_range("2023-01-01", periods=load_inputs()["n"], freq="h")
    working = np.isin(t.hour, hours) & (t.dayofweek < 5)
    activity = np.where(vacation_mask(t.month.values, t.day.values), VACATION_ACTIVITY, 1.0)
    return float(np.sum(working * activity)) * 3600.0 / WINDOW_S


_MICRO = {}


def micro_damage(wins, e_kwh, tau_s):
    """
    Battery wear from the second-by-second cycles of one window (median of
    the windows), as (upper, lower) bounds. tau_s = 0 means no SC.

    These cycles are far shallower than the datasheet's lowest point
    (20 % DoD), so the cycle-life curve has to be extended below it:
      upper  the datasheet's log-log slope carried on down - shallow cycles
             wear more per kWh, as they already do between 20 and 50 %
      lower  constant wear per kWh below 20 % DoD, the throughput view
    The window's slow drift is removed first: the hourly model counts that.
    """
    key = (round(e_kwh, 3), tau_s)
    if key in _MICRO:
        return _MICRO[key]
    d0, n0 = BATT_CYCLE_LIFE[0]
    up, lo = [], []
    for p in wins:
        pb = p if tau_s == 0 else low_pass(p, tau_s)
        soc = -np.cumsum(pb) / 3600.0 / e_kwh
        soc -= np.linspace(soc[0], soc[-1], len(soc))
        depth, count = rainflow_cycles(soc)
        depth, count = depth[depth > 0], count[depth > 0]
        n_up = cycles_to_failure(depth)
        n_lo = np.where(depth < d0, n0 * d0 / depth, n_up)
        up.append(np.sum(count / n_up))
        lo.append(np.sum(count / n_lo))
    _MICRO[key] = (float(np.median(up)), float(np.median(lo)))
    return _MICRO[key]


def npc_battery_only(opt, nb, life):
    return compute_npc(opt.pv_kw, nb, 0, opt.converter_kw, life)[0]


def sc_saving(opt, nb, tau_s, wins, n_win):
    """
    NPC an SC with filter tau_s saves on a bank of nb strings by slowing its
    wear, as (upper, lower) bounds, plus battery life without and with it.
    Wear = hourly cycles + second-scale cycles; life is capped at float
    life, which no SC can extend.
    """
    r = simulate(opt.pv_kw, nb, 0, converter_kw=opt.converter_kw, full=True)
    d_hourly = cycle_damage(r["soc_series"] / r["e_batt_kwh"])
    e = nb * BATT_KWH_PER_STRING
    without, with_sc = micro_damage(wins, e, 0), micro_damage(wins, e, tau_s)
    saved, lives = [], []
    for b in (0, 1):
        life_b = min(BATT_FLOAT_LIFE_YEARS, 1.0 / (d_hourly + n_win * without[b]))
        life_sc = min(BATT_FLOAT_LIFE_YEARS, 1.0 / (d_hourly + n_win * with_sc[b]))
        saved.append(npc_battery_only(opt, nb, life_b) - npc_battery_only(opt, nb, life_sc))
        lives.append((life_b, life_sc))
    return saved, lives


def fig_payback(opt, df, wins, n_win):
    cost = df.groupby("tau_s").cost_inr.median()
    taus = np.array(TAUS_S)
    res = [sc_saving(opt, opt.batt_strings, tau, wins, n_win) for tau in taus]
    up = np.array([s[0] for s, _ in res]) / 1e6
    lo = np.array([s[1] for s, _ in res]) / 1e6

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 4.4))
    a1.plot(taus, cost.loc[taus] / 1e6, color=SC, lw=2, marker="o", ms=5, label="SC + DC-DC cost")
    a1.fill_between(taus, np.maximum(lo, 1e-3), up, color=BATT, alpha=0.2, lw=0,
                    label="NPC saved, down to the lower bound")
    a1.plot(taus, up, color=BATT, lw=2, marker="o", ms=5,
            label="NPC saved, upper bound")
    a1.set_xscale("log")
    a1.set_yscale("log")
    a1.set_xlabel("Filter time constant τ (s, log)")
    a1.set_ylabel("₹ million (log)")
    title(a1, f"This design ({opt.batt_kwh/1000:.1f} MWh): at best the SC breaks even, at τ ≈ 1-2 s")
    a1.legend(frameon=False, fontsize=8.5, loc="upper left")
    style(a1)

    strings = np.unique(np.round(np.logspace(0, np.log10(opt.batt_strings * 1.5), 25)).astype(int))
    res = [sc_saving(opt, nb, PAYBACK_TAU_S, wins, n_win)[0] for nb in strings]
    up_b = np.array([s[0] for s in res]) / 1e6
    lo_b = np.array([s[1] for s in res]) / 1e6
    mwh = strings * BATT_KWH_PER_STRING / 1000
    c = cost.loc[PAYBACK_TAU_S] / 1e6
    a2.fill_between(mwh, np.maximum(lo_b, 1e-3), np.maximum(up_b, 1e-3), color=BATT, alpha=0.2, lw=0)
    a2.plot(mwh, np.maximum(up_b, 1e-3), color=BATT, lw=2, label="NPC saved, upper bound")
    a2.axhline(c, color=SC, lw=2, label=f"SC + DC-DC cost, τ = {PAYBACK_TAU_S} s")
    a2.axvline(opt.batt_kwh / 1000, color=INK, ls=":", lw=1.2)
    a2.text(opt.batt_kwh / 1000 * 0.92, 15, "this design", ha="right", fontsize=8.5, color=INK)
    a2.set_xscale("log")
    a2.set_yscale("log")
    a2.set_ylim(1e-3, 30)
    a2.set_xlabel("Battery bank (MWh, log)")
    a2.set_ylabel("₹ million (log)")
    # a small bank wears more per kWh, but is cheaper to replace
    title(a2, "A smaller bank saves fewer rupees, not more")
    a2.legend(frameon=False, fontsize=8.5, loc="lower left")
    style(a2)
    save(fig, "sc_payback.png")
    pays = mwh[up_b >= c]
    return res, pays


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

    n_win = switching_windows_per_year()
    fig_payback(opt, df, wins, n_win)

    med = df.groupby("tau_s").median(numeric_only=True)
    print(f"\n  {n_win:,.0f} switching windows a year; battery float life "
          f"{BATT_FLOAT_LIFE_YEARS:.1f} y\n")
    print("  tau (s)  strings  cost ₹M  ramp %   life without -> with SC (y)   NPC saved ₹M")
    for tau, r in med.iterrows():
        saved, lives = sc_saving(opt, opt.batt_strings, tau, wins, n_win)
        print(f"  {tau:7.0f}  {r.strings:7.0f}  {r.cost_inr/1e6:7.1f}  {r.batt_ramp_pct:6.0f}"
              f"   {lives[0][0]:.2f} -> {lives[0][1]:.2f}  (lower {lives[1][0]:.2f} -> {lives[1][1]:.2f})"
              f"   {saved[1]/1e6:.2f} - {saved[0]/1e6:.2f}")
    print(f"\n  median surge above the window mean: {peak:.0f} kW")


if __name__ == "__main__":
    main()
