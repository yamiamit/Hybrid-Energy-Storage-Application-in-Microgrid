"""
Step 2 - The simulator.

One function, called thousands of times by the optimiser:

    simulate(pv_kw, n_batt_strings, n_sc_strings, converter_kw)
        ->  NPC, LPSP, score

It runs the system hour by hour for a full year, tracks battery state of
charge, counts unmet energy, then costs the design over the project life.

Decision variables
    pv_kw           installed PV capacity, kW            (continuous)
    n_batt_strings  battery strings, 20 x 3 kWh each     (integer)
    n_sc_strings    supercapacitor strings               (integer)
    converter_kw    battery converter rating, kW         (continuous)
                    optional - defaults to 1.1 x peak load

Topology (AC-coupled, as in Kumar et al.)
    PV has its own inverter, included in the CERC all-in PV price, and
    feeds the AC bus directly. The battery sits behind the bidirectional
    converter, so every kWh into or out of it pays the converter efficiency
    and is capped by the converter rating.

Outputs
    NPC    net present cost over the project life, INR
    LPSP   loss of power supply probability, 0 to 1
    score  what PSO minimises: NPC for a feasible design, and for an
           infeasible one a value above every feasible NPC, growing with
           how badly the constraints are broken

Run from the project root:
    python src/simulator.py          # runs the verification suite
"""

import numpy as np
import pandas as pd

from costs import (PV, BATTERY_LA, CONVERTER, SUPERCAP, ECON,
                   sc_strings_for_energy, sc_modules_in_series)
from prepare_data import SPEC_FILE, TRANSIENT_DURATION_S

INPUT_FILE = "data/inputs.csv"

# =====================================================================
# CONFIG
# =====================================================================

LPSP_TARGET = 0.01          # reliability constraint: <= 1 % unmet energy
PENALTY = 1e10              # must exceed any feasible NPC

# Worst-case transient written by prepare_data.py, in joules.
# This is what the supercapacitor bank must be able to absorb.
TRANSIENT_J = pd.read_csv(SPEC_FILE)["scaled_kw"].sum() * 1000.0 * TRANSIENT_DURATION_S

# PV model, eq. (3) of Kumar et al.
NOCT_C = 45.0               # nominal operating cell temperature
G_STC = 1000.0              # W/m2

# Converter sized to the peak load with headroom
CONVERTER_OVERSIZE = 1.10

# --- PLACEHOLDER: replace once you have a supplier quote -------------
# costs.py deliberately leaves this as None. Nothing reported from this
# simulator is defensible until a real price goes in.
SC_PRICE_PER_MODULE_PLACEHOLDER = 45_000.0

# --- PLACEHOLDER: lead-acid lifetime throughput ----------------------
# HOMER's approach: a battery dies after a fixed amount of energy has
# passed through it, or after its float life, whichever comes first.
# Get the real figure from the Discover 12VRE-3000TF-L datasheet.
BATT_LIFETIME_THROUGHPUT_KWH = 2_250.0   # per 3 kWh battery
BATT_FLOAT_LIFE_YEARS = 10.0

BATT_KWH_PER_STRING = BATTERY_LA["nominal_capacity_kwh"] * BATTERY_LA["string_size"]

# Datasheet current limits, as power at the battery terminals.
# 57 A x 12 V = 0.684 kW charge, 133.9 A x 12 V = 1.607 kW discharge,
# per 3 kWh battery. Over a one-hour step kW and kWh are the same number.
BATT_CHARGE_KW_PER_STRING = (BATTERY_LA["max_charge_current_a"]
                             * BATTERY_LA["nominal_voltage_v"] / 1000.0
                             * BATTERY_LA["string_size"])
BATT_DISCHARGE_KW_PER_STRING = (BATTERY_LA["max_discharge_current_a"]
                                * BATTERY_LA["nominal_voltage_v"] / 1000.0
                                * BATTERY_LA["string_size"])


# =====================================================================
# INPUTS - loaded once
# =====================================================================

_DATA = None


def load_inputs(path=INPUT_FILE):
    global _DATA
    if _DATA is None:
        df = pd.read_csv(path)
        _DATA = dict(
            ghi=df["ghi"].to_numpy(dtype=float),
            tamb=df["tamb"].to_numpy(dtype=float),
            load=df["load_kw"].to_numpy(dtype=float),
            n=len(df),
        )
    return _DATA


# =====================================================================
# PV MODEL
# =====================================================================

def pv_output_kw(pv_kw, ghi, tamb):
    """
    Kumar et al. eq. (3):
        P = RC * DF * (G/G_stc) * [1 + alpha*(T_cell - 25)]
    Cell temperature from ambient and irradiance via the NOCT model.
    """
    t_cell = tamb + (NOCT_C - 20.0) / 800.0 * ghi
    p = (pv_kw * PV["derating"] * (ghi / G_STC)
         * (1.0 + PV["temp_coeff_per_C"] * (t_cell - 25.0)))
    return np.clip(p, 0.0, None)


# =====================================================================
# HOURLY DISPATCH
# =====================================================================

def run_dispatch(pv_kw, n_batt_strings, converter_kw, data=None):
    """
    Walk the year one hour at a time. Returns a dict of annual results
    plus the SoC series, which the degradation model needs later.

    Each hour, PV serves the load directly first. A surplus charges the
    battery through the converter and the rest is curtailed; a deficit is
    drawn from the battery through the converter and the rest is unmet.
    Battery flows are capped by the converter rating, the battery's
    current limits, and the SoC window.
    """
    d = data or load_inputs()
    load = d["load"]
    n = d["n"]

    pv = pv_output_kw(pv_kw, d["ghi"], d["tamb"])

    e_batt = n_batt_strings * BATT_KWH_PER_STRING          # kWh
    soc_min = BATTERY_LA["soc_min"] * e_batt
    soc_max = e_batt
    eta_b = np.sqrt(BATTERY_LA["roundtrip_efficiency"])    # split each way
    eta_c = CONVERTER["efficiency"]
    p_chg = n_batt_strings * BATT_CHARGE_KW_PER_STRING     # at the terminals
    p_dis = n_batt_strings * BATT_DISCHARGE_KW_PER_STRING
    conv = max(0.0, converter_kw)                          # AC side

    soc = BATTERY_LA["soc_init"] * e_batt
    soc_series = np.empty(n)
    # hourly flows, kWh: PV straight to load, AC into and out of the
    # battery converter, and unmet demand
    direct_s, into_s, out_s, unmet_s = (np.zeros(n) for _ in range(4))

    pv_to_load = 0.0
    ac_to_batt = 0.0          # AC energy sent into the converter
    batt_to_load = 0.0        # AC energy delivered by the converter
    throughput = 0.0          # kWh out of the battery terminals
    unmet = 0.0
    curtailed = 0.0
    max_ac_flow = 0.0         # largest hourly converter flow, for verification
    max_charge = 0.0          # largest hourly charge at the terminals

    for t in range(n):
        direct = min(pv[t], load[t])
        pv_to_load += direct
        direct_s[t] = direct
        surplus = pv[t] - direct
        deficit = load[t] - direct

        if surplus > 0.0:
            room = (soc_max - soc) / eta_b                 # terminal kWh that fits
            terminal = min(surplus * eta_c, conv * eta_c, p_chg, room)
            ac_in = terminal / eta_c if eta_c > 0 else 0.0
            soc += terminal * eta_b
            ac_to_batt += ac_in
            into_s[t] = ac_in
            curtailed += surplus - ac_in
            max_ac_flow = max(max_ac_flow, ac_in)
            max_charge = max(max_charge, terminal)
        elif deficit > 0.0:
            available = (soc - soc_min) * eta_b            # terminal kWh on offer
            terminal = min(deficit / eta_c, conv / eta_c, p_dis, available)
            ac_out = terminal * eta_c
            soc -= terminal / eta_b
            batt_to_load += ac_out
            out_s[t] = ac_out
            throughput += terminal
            unmet += deficit - ac_out
            unmet_s[t] = deficit - ac_out
            max_ac_flow = max(max_ac_flow, ac_out)

        soc_series[t] = soc

    demand = load.sum()
    return dict(
        pv_generated=pv.sum(),
        demand=demand,
        served=pv_to_load + batt_to_load,
        pv_to_load=pv_to_load,
        ac_to_batt=ac_to_batt,
        batt_to_load=batt_to_load,
        unmet=unmet,
        curtailed=curtailed,
        throughput=throughput,
        lpsp=unmet / demand if demand > 0 else 0.0,
        soc_series=soc_series,
        pv_series=pv,
        load_series=load,
        direct_series=direct_s,
        into_batt_series=into_s,
        from_batt_series=out_s,
        unmet_series=unmet_s,
        soc_init=BATTERY_LA["soc_init"] * e_batt,
        soc_min_limit=soc_min,
        soc_max_limit=soc_max,
        e_batt=e_batt,
        peak_load=load.max(),
        max_ac_flow=max_ac_flow,
        max_charge=max_charge,
        charge_limit=p_chg,
    )


# =====================================================================
# BATTERY LIFE
# =====================================================================

def battery_life_years(n_batt_strings, annual_throughput_kwh):
    """
    Throughput model, as HOMER uses for lead-acid. Replaced by rainflow
    cycle counting in Step 7.
    """
    n_batteries = n_batt_strings * BATTERY_LA["string_size"]
    if n_batteries == 0 or annual_throughput_kwh <= 0:
        return BATT_FLOAT_LIFE_YEARS

    total_throughput = n_batteries * BATT_LIFETIME_THROUGHPUT_KWH
    throughput_life = total_throughput / annual_throughput_kwh
    return min(BATT_FLOAT_LIFE_YEARS, throughput_life)


def replacement_years(life_years, project_years):
    """Years in which a replacement is bought, e.g. [7, 14]."""
    years, y = [], life_years
    while y < project_years:
        years.append(y)
        y += life_years
    return years


def salvage_fraction(life_years, project_years):
    """
    Fraction of a component's life left when the project ends, as HOMER
    computes salvage: the last unit bought, scaled by its remaining life.
    PV with a 25-year life in a 15-year project leaves 10/25 = 0.4.
    """
    if life_years <= 0:
        return 0.0
    last_bought = 0.0
    while last_bought + life_years < project_years:
        last_bought += life_years
    return (last_bought + life_years - project_years) / life_years


def crf(r, years):
    """Capital recovery factor: turns a present cost into equal annual payments."""
    return r * (1.0 + r) ** years / ((1.0 + r) ** years - 1.0)


# =====================================================================
# COST
# =====================================================================

def compute_npc(pv_kw, n_batt_strings, n_sc_strings, converter_kw, batt_life):
    r = ECON["real_discount"]
    life = ECON["project_years"]

    n_batteries = n_batt_strings * BATTERY_LA["string_size"]
    n_sc_modules = n_sc_strings * sc_modules_in_series()
    sc_price = SUPERCAP["capital_inr_per_module"] or SC_PRICE_PER_MODULE_PLACEHOLDER

    # --- capital, spent today ---
    parts = dict(
        pv_capital=pv_kw * PV["capital_inr_per_kw"],
        battery_capital=n_batteries * BATTERY_LA["capital_inr_per_unit"],
        converter_capital=converter_kw * CONVERTER["capital_inr_per_kw"],
        sc_capital=n_sc_modules * sc_price,
    )
    capex = sum(parts.values())
    npc = capex

    # --- replacements, discounted back ---
    batt_replace_cost = n_batteries * BATTERY_LA["replacement_inr_per_unit"]
    parts["battery_replacements"] = sum(
        batt_replace_cost / (1.0 + r) ** y for y in replacement_years(batt_life, life))
    npc += parts["battery_replacements"]
    # PV and converter outlive the 15-year project; SC does > 500k cycles

    # --- annual running costs ---
    annual_om = (pv_kw * PV["om_inr_per_kw_year"]
                 + n_batteries * BATTERY_LA["om_inr_per_unit_year"]
                 + converter_kw * CONVERTER["om_inr_per_kw_year"]
                 + ECON["system_fixed_om_per_year"])
    parts["om"] = sum(annual_om / (1.0 + r) ** y for y in range(1, life + 1))
    npc += parts["om"]

    # --- salvage: life left in equipment at the end, credited back ---
    salvage = (
        pv_kw * PV["replacement_inr_per_kw"]
        * salvage_fraction(PV["lifetime_years"], life)
        + batt_replace_cost * salvage_fraction(batt_life, life)
        + converter_kw * CONVERTER["replacement_inr_per_kw"]
        * salvage_fraction(CONVERTER["lifetime_years"], life)
        + n_sc_modules * sc_price
        * salvage_fraction(SUPERCAP["lifetime_years"], life)
    )
    salvage_pv = salvage / (1.0 + r) ** life
    npc -= salvage_pv
    parts["salvage"] = -salvage_pv

    return npc, capex, annual_om, salvage_pv, parts


# =====================================================================
# THE FUNCTION THE OPTIMISER CALLS
# =====================================================================

def default_converter_kw():
    """The old fixed rule: converter sized to the peak load with headroom."""
    return load_inputs()["load"].max() * CONVERTER_OVERSIZE


def simulate(pv_kw, n_batt_strings, n_sc_strings, converter_kw=None, full=False):
    """
    Evaluate one design.
    Returns (NPC, LPSP, score), or a full result dict if full=True.
    """
    pv_kw = max(0.0, float(pv_kw))
    n_batt_strings = max(0, int(round(n_batt_strings)))
    n_sc_strings = max(0, int(round(n_sc_strings)))
    if converter_kw is None:
        converter_kw = default_converter_kw()
    converter_kw = max(0.0, float(converter_kw))

    res = run_dispatch(pv_kw, n_batt_strings, converter_kw)

    batt_life = battery_life_years(n_batt_strings, res["throughput"])
    npc, capex, annual_om, salvage, cost_parts = compute_npc(
        pv_kw, n_batt_strings, n_sc_strings, converter_kw, batt_life)

    # --- constraints folded into the score ---
    # Feasibility first: every infeasible design scores above PENALTY, so it
    # loses to every feasible one however cheap it is. Among infeasible
    # designs the smaller violation wins. A plain NPC + k * violation lets
    # a slightly unreliable design undercut a reliable one.
    sc_needed = sc_strings_for_energy(TRANSIENT_J)
    violation = (max(0.0, res["lpsp"] - LPSP_TARGET)
                 + max(0, sc_needed - n_sc_strings))
    score = npc if violation == 0.0 else PENALTY * (1.0 + violation)

    # LCOE as HOMER defines it: annualised cost over annual energy served
    served_kwh = res["served"]
    lcoe = (npc * crf(ECON["real_discount"], ECON["project_years"]) / served_kwh
            if served_kwh > 0 else float("inf"))

    if not full:
        return npc, res["lpsp"], score

    return dict(
        npc=npc, lpsp=res["lpsp"], score=score, lcoe=lcoe,
        capex=capex, annual_om=annual_om, salvage=salvage, cost_parts=cost_parts,
        pv_kw=pv_kw, n_batt_strings=n_batt_strings, n_sc_strings=n_sc_strings,
        e_batt_kwh=res["e_batt"], converter_kw=converter_kw,
        batt_life_years=batt_life,
        replacements=[round(float(y), 2) for y in
                      replacement_years(batt_life, ECON["project_years"])],
        sc_strings_needed=sc_needed,
        **{k: res[k] for k in
           ("pv_generated", "demand", "served", "pv_to_load", "ac_to_batt",
            "batt_to_load", "unmet", "curtailed", "throughput",
            "soc_series", "pv_series", "load_series", "direct_series",
            "into_batt_series", "from_batt_series", "unmet_series",
            "soc_init", "soc_min_limit", "soc_max_limit",
            "max_ac_flow", "max_charge", "charge_limit")},
    )


# =====================================================================
# STEP 3 - VERIFICATION. Do not skip.
# =====================================================================

def verify():
    d = load_inputs()
    ok = True

    def check(name, condition, detail=""):
        nonlocal ok
        status = "PASS" if condition else "FAIL"
        if not condition:
            ok = False
        print(f"  [{status}] {name}   {detail}")

    print("Verification suite")
    print(f"  input: {d['n']} hours, "
          f"peak load {d['load'].max():.1f} kW, "
          f"annual demand {d['load'].sum():,.0f} kWh\n")

    # 1. no generation, no storage -> almost everything unmet
    r = simulate(0, 0, 0, full=True)
    check("no PV, no battery -> LPSP near 1.0", r["lpsp"] > 0.99,
          f"LPSP = {r['lpsp']:.4f}")

    # 2. enormous system -> nothing unmet
    r_big = simulate(5000, 500, 10, full=True)
    check("huge PV and battery -> LPSP = 0", r_big["lpsp"] < 1e-9,
          f"LPSP = {r_big['lpsp']:.2e}")

    # 3. monotonic: more PV should not increase unmet energy
    a = simulate(400, 30, 4, full=True)
    b = simulate(800, 30, 4, full=True)
    check("doubling PV reduces LPSP", b["lpsp"] <= a["lpsp"] + 1e-12,
          f"{a['lpsp']:.4f} -> {b['lpsp']:.4f}")
    check("doubling PV raises NPC", b["npc"] > a["npc"],
          f"{a['npc']/1e6:.1f} -> {b['npc']/1e6:.1f} M INR")

    # 4. state of charge never leaves its limits
    s = a["soc_series"]
    check("SoC within [min, max] at all times",
          s.min() >= a["soc_min_limit"] - 1e-6 and s.max() <= a["soc_max_limit"] + 1e-6,
          f"min {s.min():.1f}, max {s.max():.1f}, "
          f"limits [{a['soc_min_limit']:.1f}, {a['soc_max_limit']:.1f}] kWh")

    # 5. energy balance - the strongest check, closed three ways
    eta_b = np.sqrt(BATTERY_LA["roundtrip_efficiency"])
    eta_c = CONVERTER["efficiency"]

    def rel(x, y):
        return abs(x - y) / max(abs(x), 1e-9)

    pv_split = a["pv_to_load"] + a["ac_to_batt"] + a["curtailed"]
    check("PV balance: generated = direct + to battery + curtailed",
          rel(a["pv_generated"], pv_split) < 1e-9,
          f"{a['pv_generated']:,.0f} vs {pv_split:,.0f} kWh")
    load_split = a["pv_to_load"] + a["batt_to_load"] + a["unmet"]
    check("load balance: demand = direct + from battery + unmet",
          rel(a["demand"], load_split) < 1e-9,
          f"{a['demand']:,.0f} vs {load_split:,.0f} kWh")
    d_soc = a["soc_series"][-1] - a["soc_init"]
    stored = a["ac_to_batt"] * eta_c * eta_b - a["batt_to_load"] / (eta_c * eta_b)
    check("battery balance: net stored = change in SoC",
          abs(d_soc - stored) < 1e-6 * max(a["ac_to_batt"], 1.0),
          f"dSoC {d_soc:,.1f} vs net stored {stored:,.1f} kWh")

    # 6. physical limits on battery flows
    c = simulate(3000, 10, 4, converter_kw=300, full=True)
    check("converter flow never exceeds its rating",
          c["max_ac_flow"] <= c["converter_kw"] + 1e-9,
          f"max {c['max_ac_flow']:.1f} kW, rating {c['converter_kw']:.0f} kW")
    small = simulate(3000, 10, 4, converter_kw=5000, full=True)
    check("charging never exceeds the battery current limit",
          small["max_charge"] <= small["charge_limit"] + 1e-9,
          f"max {small['max_charge']:.1f} kW, limit {small['charge_limit']:.1f} kW")
    big_conv = simulate(400, 30, 4, converter_kw=5000, full=True)
    check("a larger converter does not reduce reliability",
          big_conv["lpsp"] <= a["lpsp"] + 1e-12,
          f"{a['lpsp']:.4f} -> {big_conv['lpsp']:.4f}")

    # 7. economics against hand calculations
    r, yrs = ECON["real_discount"], ECON["project_years"]
    crf_hand = r * (1 + r) ** yrs / ((1 + r) ** yrs - 1)
    check("LCOE = NPC x CRF / annual served",
          rel(a["lcoe"], a["npc"] * crf_hand / a["served"]) < 1e-12,
          f"CRF {crf_hand:.4f}, LCOE {a['lcoe']:.2f} INR/kWh")
    pv_only = simulate(1000, 0, 4, converter_kw=0, full=True)
    salvage_hand = 1000 * PV["replacement_inr_per_kw"] * (10 / 25) / (1 + r) ** yrs
    check("PV salvage = 10/25 of its cost, discounted from year 15",
          rel(pv_only["salvage"], salvage_hand) < 1e-12,
          f"{pv_only['salvage']/1e6:.2f} M INR")

    # 8. constraints: every infeasible design scores above every feasible one
    few = simulate(400, 30, 0, full=True)
    check("too few SC strings is penalised", few["score"] >= PENALTY,
          f"needs {few['sc_strings_needed']} strings")
    check("an unreliable design scores above any feasible NPC",
          a["score"] >= PENALTY and r_big["score"] == r_big["npc"],
          f"LPSP {a['lpsp']*100:.1f}% scores {a['score']:.2e};"
          f" feasible scores its NPC")

    print("\n  " + ("ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED - fix before Step 4"))
    return ok


def demo():
    print("\nExample design")
    r = simulate(pv_kw=3000, n_batt_strings=100, n_sc_strings=4, full=True)
    print(f"  PV                   {r['pv_kw']:,.0f} kW")
    print(f"  battery              {r['n_batt_strings']} strings"
          f" = {r['e_batt_kwh']:,.0f} kWh")
    print(f"  supercapacitor       {r['n_sc_strings']} strings"
          f"  (needs {r['sc_strings_needed']})")
    print(f"  converter            {r['converter_kw']:,.0f} kW")
    print()
    print(f"  LPSP                 {r['lpsp']*100:.3f} %")
    print(f"  PV generated         {r['pv_generated']:,.0f} kWh/yr")
    print(f"  demand / served      {r['demand']:,.0f} / {r['served']:,.0f} kWh/yr")
    print(f"  curtailed            {r['curtailed']:,.0f} kWh/yr")
    print(f"  battery throughput   {r['throughput']:,.0f} kWh/yr")
    print(f"  battery life         {r['batt_life_years']:.1f} years,"
          f" replaced in years {r['replacements']}")
    print()
    print(f"  capital              {r['capex']/1e6:,.1f} M INR")
    print(f"  annual O&M           {r['annual_om']/1e6:,.2f} M INR")
    print(f"  salvage credit       {r['salvage']/1e6:,.1f} M INR (present value)")
    print(f"  NPC                  {r['npc']/1e6:,.1f} M INR")
    print(f"  LCOE                 {r['lcoe']:.2f} INR/kWh"
          f"   (paper's off-grid range: 11.96 - 18.47)")


if __name__ == "__main__":
    verify()
    demo()
