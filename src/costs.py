"""
Cost and economic parameters.

Every figure below is either taken directly from, or derived from:

  A. Kumar, A. R. Singh, Y. Deng, X. He, P. Kumar, R. C. Bansal,
  "Multiyear Load Growth Based Techno-Financial Evaluation of a Microgrid
   for an Academic Institution," IEEE Access, vol. 6, pp. 37533-37555, 2018.
  DOI: 10.1109/ACCESS.2018.2849411

  Table 2 (component costs), Section IV-C (inflation, discount, lifetime),
  Section IV-B (component descriptions).

The paper's own cost basis is the CERC benchmark tariff order:
  Determination of Levellised Generic Tariff for FY 2016-17, Central
  Electricity Regulatory Commission, Government of India, New Delhi, 2016.

Costs are in 2016-17 INR. Items marked TODO are NOT in the paper and need
their own source before the report is written.

Usage:
    from costs import PV, BATTERY_LA, CONVERTER, ECON
"""

# =====================================================================
# ECONOMICS  (Kumar et al., Section IV-C)
# =====================================================================

ECON = dict(
    # "an inflation rate of 5.71 % is considered annually over the
    #  project lifetime"
    inflation=0.0571,

    # "Based on CERC, 10.70 % has been considered as the discount factor
    #  for all the renewable energy technologies"
    nominal_discount=0.1070,

    # HOMER discounts CONSTANT-currency cash flows at the REAL rate:
    #     r_real = (1 + r_nom)/(1 + inflation) - 1
    # Use this one in the NPC calculation, not 10.70 %.
    real_discount=(1.1070 / 1.0571) - 1.0,        # = 0.04721  (4.72 %)

    # "15 years is assumed as project life in this analysis"
    project_years=15,

    # "INR 500000 is also added up to fixed O&M cost which accounts for
    #  small maintenance"  - a fixed annual cost, independent of sizing.
    # It shifts every NPC by the same amount and does not change rankings.
    system_fixed_om_per_year=500_000.0,

    # Assam State Electricity Board commercial rate; sellback assumed equal
    grid_buy_inr_per_kwh=5.96,
    grid_sell_inr_per_kwh=5.96,

    # "a 10 % annual electric load growth is considered in this research work"
    # Set to 0.0 for a static-load study; the paper's multiyear result
    # is driven by this.
    load_growth_per_year=0.10,
)


# =====================================================================
# SOLAR PV  (Table 2, row 1)
# =====================================================================
# "A fixed type SPV panel is considered with a CPC of INR 50502/kW as per
#  the benchmark capital cost by CERC. The O & M cost is taken as INR
#  700/kW per year."
#
# NOTE: this capital cost is ALL-IN. Per CERC it already includes module
# cost, civil and general works, mounting structures, the power
# conditioning unit (inverter), evacuation cost, and preliminary and
# pre-operative expenses. Land cost is NOT included.
# Do not add a separate inverter cost for the PV side.

PV = dict(
    capital_inr_per_kw=50_502.0,
    replacement_inr_per_kw=50_502.0,
    om_inr_per_kw_year=700.0,
    lifetime_years=25,          # TODO: not stated in the paper; CERC default
    derating=0.85,              # TODO: DF_SPV appears in eq. (3), value not given
    temp_coeff_per_C=-0.0040,   # TODO: alpha_p in eq. (3), value not given
)


# =====================================================================
# BATTERY - tubular flooded lead-acid  (Table 2, row 6)
# =====================================================================
# "Tubular flooded lead-acid batteries (Discover 12VRE-3000TF-L) which can
#  provide lowest cost/kWh and is suitable especially for off-grid
#  applications is considered as storage."
# "A string size of 20 is taken with an initial state of charge as 100 %
#  and minimum state of charge as 20 %."

BATTERY_LA = dict(
    label="Discover 12VRE-3000TF-L, tubular flooded lead-acid",
    nominal_voltage_v=12.0,
    nominal_capacity_kwh=3.0,
    max_capacity_ah=244.97,
    capacity_ratio=0.329,           # kinetic battery model, c
    rate_constant_per_hr=0.597,     # kinetic battery model, k
    roundtrip_efficiency=0.85,
    max_charge_current_a=57.0,
    max_discharge_current_a=133.9,
    max_charge_rate_a_per_ah=1.0,

    capital_inr_per_unit=22_000.0,
    replacement_inr_per_unit=22_000.0,
    om_inr_per_unit_year=700.0,

    soc_min=0.20,
    soc_init=1.00,
    string_size=20,

    # derived: 22000 / 3 kWh
    capital_inr_per_kwh=22_000.0 / 3.0,        # = 7333 INR/kWh

    # Cycle life against depth of discharge, at 20 C. Not in the paper.
    # Source: Discover Energy, "12VRE-3000TF-L Tubular Flooded RE Series"
    # datasheet, updated 12 Nov 2013 - the exact model Kumar et al. use.
    # (depth of discharge as a fraction of rated capacity, cycles to end of life)
    cycle_life=((0.20, 5000), (0.50, 2500), (0.80, 1500)),
    # The 12VRE-3000TF (OPzS) datasheet of 7 May 2018 quotes fewer cycles. Kept as
    # the pessimistic case for the sensitivity study.
    cycle_life_later_sheet=((0.20, 4500), (0.50, 2000), (0.80, 1100)),
    internal_resistance_ohm=0.005,      # RINT, same 2013 datasheet

    # Expected service (float) life against operating temperature, 12 V
    # blocks, read off the lower (pessimistic) edge of the band in the same
    # datasheet's graph. 18 years at 20 C and below; roughly halves every 8 C.
    # (temperature C, years)
    service_life=((20.0, 18.0), (22.5, 15.0), (25.0, 12.5), (27.5, 10.5),
                  (30.0, 8.8), (32.5, 7.4), (35.0, 6.1), (37.5, 5.1),
                  (40.0, 4.3), (45.0, 3.0), (50.0, 2.1), (55.0, 1.5)),
)


# =====================================================================
# BIDIRECTIONAL CONVERTER  (Table 2, row 5)
# =====================================================================
# "The CPC is considered to be INR 10000/kW. Currently, available
#  converters in the market are maintenance free for their lifetime,
#  so the O & M cost is considered to be zero."

CONVERTER = dict(
    capital_inr_per_kw=10_000.0,
    replacement_inr_per_kw=10_000.0,
    om_inr_per_kw_year=0.0,
    lifetime_years=15,          # TODO: not stated; assumed equal to project life
    efficiency=0.95,            # TODO: not stated in the paper
)


# =====================================================================
# SUPERCAPACITOR  --  NOT IN THE PAPER.  NEEDS ITS OWN SOURCE.
# =====================================================================
# Kumar et al. model battery storage only. Every number here is a
# placeholder and MUST be replaced with a supplier quotation or a cited
# paper before any result is reported.
#
# Priced per MODULE, not per kWh. A supercapacitor costs enormously more
# per kWh than a battery and enormously less per kW - which is the whole
# reason the hybrid exists. Pricing it per kWh will mislead you.
#
# Usable energy of one module, discharging to half rated voltage:
#     E = 0.5 * C * (V_max^2 - V_min^2)
# For 16 V, 58 F with V_min = 8 V:
#     E = 0.5 * 58 * (256 - 64) = 5568 J = 1.55 Wh

SUPERCAP = dict(
    label="TODO - e.g. 16 V / 58 F module, confirm part and price",
    module_voltage_v=16.0,
    module_capacitance_f=58.0,
    v_min_fraction=0.5,             # discharge to half rated voltage
    esr_ohm=None,                   # TODO from datasheet
    roundtrip_efficiency=0.97,      # TODO confirm

    capital_inr_per_module=None,    # TODO - supplier quote
    replacement_inr_per_module=None,
    om_inr_per_module_year=None,
    lifetime_years=15,              # effectively project life; >500k cycles

    # bus voltage decides how many modules go in series
    bus_voltage_v=380.0,
)


def sc_module_energy_j(sc=SUPERCAP):
    """Usable energy of one supercapacitor module, in joules."""
    v = sc["module_voltage_v"]
    return 0.5 * sc["module_capacitance_f"] * (v**2 - (v * sc["v_min_fraction"])**2)


def sc_modules_in_series(sc=SUPERCAP):
    """Modules needed in series to reach the DC bus voltage."""
    import math
    return math.ceil(sc["bus_voltage_v"] / sc["module_voltage_v"])


def sc_strings_for_energy(required_j, sc=SUPERCAP):
    """Parallel strings needed to deliver required_j joules."""
    import math
    per_string = sc_module_energy_j(sc) * sc_modules_in_series(sc)
    return math.ceil(required_j / per_string)


# =====================================================================
# BENCHMARKS from the same paper - sanity-check your own results
# =====================================================================
# Table 4. Off-grid scenarios 1-8, whole campus, 15-year life, 10 % growth.

BENCHMARK = dict(
    offgrid_npc_million_inr=(5835, 9009),
    offgrid_capital_million_inr=(4119, 7290),
    offgrid_om_million_inr=(998, 1756),
    offgrid_lcoe_inr_per_kwh=(11.96, 18.47),

    gridconnected_npc_million_inr=(169, 1004),
    gridconnected_lcoe_inr_per_kwh=(0.18, 1.39),

    # renewable fraction
    offgrid_rf_pct=(92, 100),
    gridconnected_rf_pct=(63, 80),

    # best off-grid: scenario 8 (SPV + BG + DG + LAB), load-following
    best_offgrid=dict(npc_million_inr=5835, lcoe_inr_per_kwh=11.96, rf_pct=95),
)


if __name__ == "__main__":
    print(f"real discount rate      {ECON['real_discount']*100:.2f} %"
          f"   (nominal {ECON['nominal_discount']*100:.2f} %,"
          f" inflation {ECON['inflation']*100:.2f} %)")
    print(f"project life            {ECON['project_years']} years")
    print(f"PV capital              {PV['capital_inr_per_kw']:,.0f} INR/kW (all-in)")
    print(f"lead-acid battery       {BATTERY_LA['capital_inr_per_kwh']:,.0f} INR/kWh")
    print(f"bidirectional converter {CONVERTER['capital_inr_per_kw']:,.0f} INR/kW")
    print(f"grid tariff             {ECON['grid_buy_inr_per_kwh']:.2f} INR/kWh")
    print()
    print(f"SC module usable energy {sc_module_energy_j():,.0f} J"
          f"  ({sc_module_energy_j()/3600:.2f} Wh)")
    print(f"modules in series @ {SUPERCAP['bus_voltage_v']:.0f} V bus: "
          f"{sc_modules_in_series()}")
    print(f"strings for a 465 kJ transient: {sc_strings_for_energy(465_000)}")
    print()
    print("benchmark off-grid LCOE (whole campus, same site):"
          f" {BENCHMARK['offgrid_lcoe_inr_per_kwh'][0]:.2f}"
          f" - {BENCHMARK['offgrid_lcoe_inr_per_kwh'][1]:.2f} INR/kWh")
