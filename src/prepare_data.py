"""
Step 1 - Data preparation.

Builds a one-year hourly load profile for the IIT Guwahati campus from the
bottom up: department by department, from their labs, workshops and
continuously-running equipment. The result is then calibrated against the
published campus statistics.

Two distinct outputs:

  1. ENERGY   an 8760-hour series (data/inputs.csv) used by the simulator.
  2. TRANSIENT the worst-case sub-second step, which an hourly series cannot
     represent. Written to data/transient_spec.csv and used later to size
     the supercapacitor bank analytically.

Calibration reference:
  A. Kumar, A. R. Singh, Y. Deng, X. He, P. Kumar, R. C. Bansal,
  "Multiyear Load Growth Based Techno-Financial Evaluation of a Microgrid
   for an Academic Institution," IEEE Access, vol. 6, pp. 37533-37555, 2018.
  DOI: 10.1109/ACCESS.2018.2849411
  Reported: peak 3075 kW, mean 2515.8 kW, load factor 0.82, ~60379 kWh/day.

Facility composition from IIT Guwahati public pages:
  Central Workshop (Mech): CNC lathe, CNC milling, wire-cut EDM, die-sinking
  EDM, gas/TIG/MAG/submerged-arc/SMAW welding, foundry melting and pouring.
  Central Instruments Facility: 26 analytical instruments over two ~1600 m2
  floors, including a 400 MHz FT-NMR and an SEM, serving 11 of 14 departments.

Equipment power ratings are engineering estimates for machines of the stated
type, not metered values. They are declared here so they can be replaced with
measured data if it becomes available.

Run from the project root:
    python src/prepare_data.py
"""

import numpy as np
import pandas as pd

RAW_FILE = "data/nasa_power_raw.csv"
OUT_FILE = "data/inputs.csv"
SPEC_FILE = "data/transient_spec.csv"

# =====================================================================
# CONFIG
# =====================================================================

# MODE = "campus"  -> all departments, calibrated to the published peak
# MODE = "subset"  -> only the departments named below, at their TRUE ratings.
#                     No scaling is applied, so every machine keeps its real
#                     kW and the worst-case transient is physically meaningful.
MODE = "subset"
SUBSET = ["Mechanical Engineering + Central Workshop",
          "Electronics and Electrical Engineering"]

RANDOM_SEED = 42
HOURLY_NOISE_PCT = 0.05

# Published campus reference, used to calibrate the bottom-up model
REF_PEAK_KW = 3075.0
REF_MEAN_KW = 2515.8

# How many transient machines can credibly switch together
TRANSIENT_SIMULTANEITY = 4
TRANSIENT_DURATION_S = 5.0

# Occupancy shape for academic spaces: lighting, HVAC, offices, teaching.
# Never reaches zero - corridor lighting and ventilation run overnight.
OCCUPANCY_SHAPE = [
    0.62, 0.58, 0.56, 0.55, 0.56, 0.62,   # 00-05
    0.70, 0.80, 0.90, 0.96, 1.00, 0.99,   # 06-11
    0.94, 0.97, 0.99, 0.96, 0.92, 0.86,   # 12-17
    0.80, 0.76, 0.73, 0.70, 0.67, 0.64,   # 18-23
]

# Residential (hostels, staff quarters): evening and night dominated
RESIDENTIAL_SHAPE = [
    0.74, 0.70, 0.66, 0.64, 0.65, 0.72,   # 00-05
    0.82, 0.88, 0.80, 0.72, 0.68, 0.67,   # 06-11
    0.70, 0.68, 0.67, 0.69, 0.74, 0.84,   # 12-17
    0.93, 0.99, 1.00, 0.98, 0.91, 0.82,   # 18-23
]

# Guwahati seasonality: hot Apr-Jun, monsoon Jun-Sep, mild winter
MONTHLY_FACTOR = [0.88, 0.90, 0.96, 1.06, 1.12, 1.10,
                  1.08, 1.08, 1.04, 0.98, 0.90, 0.86]

# Academic calendar: mid-Dec to early Jan and mid-May to late Jul are
# vacation, when labs and workshops run well below term-time levels.
VACATION_ACTIVITY = 0.45          # multiplier on equipment during vacation
VACATION_PERIODS = [(12, 15, 1, 5), (5, 15, 7, 20)]   # (m1,d1,m2,d2)


# ---------------------------------------------------------------------
# Equipment entry:
#   name, count, kw (rated draw while running), duty (fraction of an
#   operating hour actually drawing), hours (operating window),
#   weekdays_only, transient (True if switching causes a fast step)
# ---------------------------------------------------------------------
WORK = list(range(9, 18))        # 09:00-17:00
EXTENDED = list(range(9, 21))    # research labs run later
ALLDAY = list(range(0, 24))


def eq(name, count, kw, duty, hours, weekdays_only=True, transient=False):
    return dict(name=name, count=count, kw=kw, duty=duty, hours=hours,
                weekdays_only=weekdays_only, transient=transient)


DEPARTMENTS = {
    "Mechanical Engineering + Central Workshop": dict(
        space_kw=210, space_shape="academic", continuous_kw=18,
        equipment=[
            eq("CNC lathe",              3, 15.0, 0.45, WORK, transient=True),
            eq("CNC vertical milling",   2, 18.0, 0.45, WORK, transient=True),
            eq("Wire-cut EDM",           1, 10.0, 0.60, WORK, transient=True),
            eq("Die-sinking EDM",        1,  8.0, 0.55, WORK, transient=True),
            eq("SMAW welding set",       6, 14.0, 0.25, WORK, transient=True),
            eq("TIG/MAG welding set",    3, 12.0, 0.30, WORK, transient=True),
            eq("Foundry melting furnace", 1, 35.0, 0.35, WORK, transient=True),
            eq("Conventional lathe/mill", 8, 5.5, 0.35, WORK, transient=True),
            eq("Compressor (shop air)",  2, 15.0, 0.50, EXTENDED, transient=True),
        ]),

    "Chemical Engineering": dict(
        space_kw=165, space_shape="academic", continuous_kw=22,
        equipment=[
            eq("Pilot plant pumps",      6,  7.5, 0.55, EXTENDED, transient=True),
            eq("Process compressor",     2, 18.0, 0.45, EXTENDED, transient=True),
            eq("Tubular/muffle furnace", 5,  9.0, 0.60, EXTENDED),
            eq("Distillation reboiler",  2, 20.0, 0.40, WORK, transient=True),
            eq("Fume hood extraction",  10,  1.5, 0.85, ALLDAY, weekdays_only=False),
        ]),

    "Civil Engineering": dict(
        space_kw=150, space_shape="academic", continuous_kw=10,
        equipment=[
            eq("Universal testing machine", 2, 22.0, 0.25, WORK, transient=True),
            eq("Compression testing rig",   2, 15.0, 0.25, WORK, transient=True),
            eq("Shaking table / actuator",  1, 30.0, 0.15, WORK, transient=True),
            eq("Concrete mixer and curing", 3,  6.0, 0.40, WORK, transient=True),
            eq("Environmental chamber",     2,  5.0, 0.70, ALLDAY, weekdays_only=False),
        ]),

    "Electronics and Electrical Engineering": dict(
        space_kw=175, space_shape="academic", continuous_kw=28,
        equipment=[
            eq("Motor-generator set",       4, 15.0, 0.30, WORK, transient=True),
            eq("Power electronics test bench", 8, 6.0, 0.45, EXTENDED, transient=True),
            eq("High-voltage test set",     1, 25.0, 0.15, WORK, transient=True),
            eq("Programmable DC load/source", 6, 5.0, 0.40, EXTENDED, transient=True),
            eq("Instrumentation and racks", 1, 12.0, 0.90, ALLDAY, weekdays_only=False),
        ]),

    "Chemistry": dict(
        space_kw=155, space_shape="academic", continuous_kw=30,
        equipment=[
            eq("Fume hood extraction",     16,  1.5, 0.85, ALLDAY, weekdays_only=False),
            eq("Rotary evaporator",         8,  1.5, 0.50, EXTENDED),
            eq("Hot air oven / furnace",    6,  6.0, 0.55, EXTENDED),
            eq("Ultra-low freezer",         4,  1.2, 0.80, ALLDAY, weekdays_only=False),
            eq("Vacuum pump",              10,  1.1, 0.55, EXTENDED, transient=True),
        ]),

    "Physics": dict(
        space_kw=140, space_shape="academic", continuous_kw=45,
        equipment=[
            eq("Cryostat / He compressor",  2, 12.0, 0.85, ALLDAY, weekdays_only=False),
            eq("High-vacuum pump station",  5,  4.0, 0.70, EXTENDED, transient=True),
            eq("Laser system and chiller",  4,  6.0, 0.50, EXTENDED),
            eq("Magnet power supply",       1, 20.0, 0.25, WORK, transient=True),
            eq("Thin-film deposition",      2,  8.0, 0.45, EXTENDED, transient=True),
        ]),

    "Biosciences and Bioengineering": dict(
        space_kw=145, space_shape="academic", continuous_kw=42,
        equipment=[
            eq("Cold room / walk-in chiller", 3, 6.0, 0.80, ALLDAY, weekdays_only=False),
            eq("CO2 incubator",            10,  0.8, 0.85, ALLDAY, weekdays_only=False),
            eq("Autoclave",                 3,  9.0, 0.35, WORK, transient=True),
            eq("Refrigerated centrifuge",   6,  3.5, 0.30, EXTENDED, transient=True),
            eq("Ultra-low freezer",         6,  1.2, 0.80, ALLDAY, weekdays_only=False),
        ]),

    "Computer Science and Engineering": dict(
        space_kw=135, space_shape="academic", continuous_kw=30,
        equipment=[
            eq("HPC cluster",   1, 55.0, 0.75, ALLDAY, weekdays_only=False),
            eq("Server room CRAC", 2, 14.0, 0.80, ALLDAY, weekdays_only=False),
            eq("Teaching lab workstations", 1, 18.0, 0.55, EXTENDED),
        ]),

    "Design": dict(
        space_kw=95, space_shape="academic", continuous_kw=8,
        equipment=[
            eq("CNC router",        1, 9.0, 0.35, WORK, transient=True),
            eq("Laser cutter",      2, 5.0, 0.40, WORK, transient=True),
            eq("3D printer farm",   1, 6.0, 0.55, EXTENDED),
            eq("Spray booth / extraction", 1, 4.0, 0.35, WORK, transient=True),
        ]),

    "Central Instruments Facility": dict(
        space_kw=120, space_shape="academic", continuous_kw=38,
        equipment=[
            eq("400 MHz FT-NMR (cooling)", 1, 14.0, 0.95, ALLDAY, weekdays_only=False),
            eq("SEM / FESEM",              2,  6.0, 0.55, EXTENDED),
            eq("Powder XRD",               2,  5.0, 0.55, EXTENDED),
            eq("Chiller for instruments",  3,  8.0, 0.75, ALLDAY, weekdays_only=False),
            eq("Other analytical instruments", 18, 1.2, 0.45, EXTENDED),
        ]),

    "Mathematics, HSS and Centres": dict(
        space_kw=130, space_shape="academic", continuous_kw=12,
        equipment=[
            eq("Computing and office equipment", 1, 22.0, 0.55, EXTENDED),
        ]),

    "Hostels and residences": dict(
        space_kw=620, space_shape="residential", continuous_kw=60,
        equipment=[
            eq("Water pumping station", 4, 18.0, 0.35, ALLDAY,
               weekdays_only=False, transient=True),
            eq("Mess kitchen equipment", 1, 45.0, 0.40, [6,7,8,11,12,13,18,19,20],
               weekdays_only=False, transient=True),
            eq("Laundry", 1, 12.0, 0.30, list(range(8, 20)), weekdays_only=False),
        ]),

    "Campus services and lighting": dict(
        space_kw=180, space_shape="residential", continuous_kw=55,
        equipment=[
            eq("Street lighting", 1, 70.0, 0.95,
               [18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5], weekdays_only=False),
            eq("STP / WTP pumps", 3, 15.0, 0.55, ALLDAY,
               weekdays_only=False, transient=True),
            eq("Lifts and misc motors", 1, 25.0, 0.35, list(range(7, 22)),
               weekdays_only=False, transient=True),
        ]),
}

# =====================================================================


def read_nasa_power(path):
    """NASA POWER CSVs carry a metadata block before the real header."""
    with open(path) as f:
        lines = f.readlines()
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith("YEAR"):
            start = i
            break
    if start is None:
        raise ValueError("Could not find the data header in the NASA file.")

    df = pd.read_csv(path, skiprows=start)
    df = df.rename(columns={"ALLSKY_SFC_SW_DWN": "ghi", "T2M": "tamb"})
    df[["ghi", "tamb"]] = df[["ghi", "tamb"]].replace(-999.0, np.nan)
    df[["ghi", "tamb"]] = df[["ghi", "tamb"]].interpolate(limit_direction="both")
    df["ghi"] = df["ghi"].clip(lower=0.0)
    return df[["YEAR", "MO", "DY", "HR", "ghi", "tamb"]].reset_index(drop=True)


def vacation_mask(months, days):
    m = np.zeros(months.size, dtype=bool)
    for m1, d1, m2, d2 in VACATION_PERIODS:
        if m1 <= m2:
            m |= (((months == m1) & (days >= d1)) |
                  ((months > m1) & (months < m2)) |
                  ((months == m2) & (days <= d2)))
        else:                               # wraps the year end
            m |= (((months == m1) & (days >= d1)) | (months > m1) |
                  (months < m2) | ((months == m2) & (days <= d2)))
    return m


def equipment_load(item, hod, is_weekday, activity, rng):
    """Average power over each hour, in kW."""
    active = np.isin(hod, item["hours"])
    if item["weekdays_only"]:
        active = active & is_weekday

    # how many units are running varies hour to hour
    running = rng.binomial(item["count"], 0.65, size=hod.size).astype(float)
    if item["count"] == 1:
        running = np.ones(hod.size)

    load = running * item["kw"] * item["duty"]
    load = np.where(active, load, 0.0)

    # continuously-rated kit keeps running through vacation
    if item["hours"] is ALLDAY and not item["weekdays_only"]:
        return load
    return load * activity


def build_campus(df, rng):
    n = len(df)
    hod = df["HR"].to_numpy(dtype=int)
    months = df["MO"].to_numpy(dtype=int)
    days = df["DY"].to_numpy(dtype=int)

    try:
        dates = pd.to_datetime(dict(year=df["YEAR"], month=df["MO"], day=df["DY"]))
        is_weekday = (dates.dt.dayofweek < 5).to_numpy()
    except Exception:
        print("  note: could not parse dates, using a day index for weekdays")
        is_weekday = ((np.arange(n) // 24) % 7) < 5

    on_vac = vacation_mask(months, days)
    activity = np.where(on_vac, VACATION_ACTIVITY, 1.0)
    monthly = np.asarray(MONTHLY_FACTOR)[months - 1]

    shapes = {"academic": np.asarray(OCCUPANCY_SHAPE),
              "residential": np.asarray(RESIDENTIAL_SHAPE)}

    cols, transients = {}, []
    for dept, cfg in DEPARTMENTS.items():
        shape = shapes[cfg["space_shape"]][hod]
        space = cfg["space_kw"] * shape * monthly
        if cfg["space_shape"] == "academic":
            space = space * np.where(on_vac, 0.80, 1.0)

        total = space + cfg["continuous_kw"]
        for item in cfg["equipment"]:
            total = total + equipment_load(item, hod, is_weekday, activity, rng)
            if item["transient"]:
                transients.append((dept, item["name"], item["kw"]))

        total *= 1.0 + rng.uniform(-HOURLY_NOISE_PCT, HOURLY_NOISE_PCT, size=n)
        cols[dept] = np.clip(total, 0.0, None)

    return cols, transients


def main():
    df = read_nasa_power(RAW_FILE)
    n = len(df)
    print(f"Read {n} hourly rows from {RAW_FILE}")
    if n not in (8760, 8784):
        print(f"  warning: expected 8760 (or 8784 in a leap year), got {n}")

    rng = np.random.default_rng(RANDOM_SEED)
    cols, transients = build_campus(df, rng)

    raw_total = sum(cols.values())
    print(f"\nBottom-up model before calibration:")
    print(f"  peak {raw_total.max():.0f} kW, mean {raw_total.mean():.0f} kW, "
          f"LF {raw_total.mean()/raw_total.max():.3f}")
    print(f"  published reference: peak {REF_PEAK_KW:.0f} kW, "
          f"mean {REF_MEAN_KW:.1f} kW, LF {REF_MEAN_KW/REF_PEAK_KW:.3f}")
    print(f"  VALIDATION - mean is within {abs(raw_total.mean()-REF_MEAN_KW)/REF_MEAN_KW*100:.1f}%"
          f" of published, and was not fitted to it")

    cal = REF_PEAK_KW / raw_total.max()
    print(f"  calibration factor to published peak: {cal:.3f}")

    if MODE == "campus":
        scale = cal
        print(f"  MODE=campus: all departments, scaled by {scale:.3f}")
    else:
        scale = 1.0
        missing = [d for d in SUBSET if d not in cols]
        if missing:
            raise KeyError(f"unknown department(s): {missing}")
        cols = {k: v for k, v in cols.items() if k in SUBSET}
        print(f"  MODE=subset: {len(cols)} department(s), true machine ratings,"
              f" no scaling")

    for k in cols:
        cols[k] = cols[k] * scale
    campus = sum(cols.values())

    out = pd.DataFrame({"hour": np.arange(n),
                        "ghi": df["ghi"].to_numpy(),
                        "tamb": df["tamb"].to_numpy(),
                        "load_kw": campus})
    for k, v in cols.items():
        out["dept_" + k.split()[0].lower().strip(",")] = v
    out.to_csv(OUT_FILE, index=False)

    # ---- worst-case transient ----
    if MODE == "subset":
        transients = [t for t in transients if t[0] in SUBSET]
    transients.sort(key=lambda t: -t[2])
    top = transients[:TRANSIENT_SIMULTANEITY]
    step_kw = sum(t[2] for t in top) * scale
    step_kj = step_kw * TRANSIENT_DURATION_S

    pd.DataFrame([{"department": d, "machine": m,
                   "rated_kw": k, "scaled_kw": k * scale} for d, m, k in top]
                 ).to_csv(SPEC_FILE, index=False)

    steps = np.abs(np.diff(campus))
    print(f"\nWrote {OUT_FILE} and {SPEC_FILE}")
    print("  --- solar ---")
    print(f"  annual irradiation   {out['ghi'].sum()/1000:8.1f} kWh/m2")
    print(f"  peak GHI             {out['ghi'].max():8.1f} W/m2")
    print(f"  mean temperature     {out['tamb'].mean():8.1f} degC")
    print("  --- load ---")
    print(f"  annual demand        {campus.sum():8.0f} kWh")
    print(f"  daily mean           {campus.sum()/365:8.0f} kWh/day")
    print(f"  peak / mean          {campus.max():8.1f} / {campus.mean():.1f} kW")
    print(f"  load factor          {campus.mean()/campus.max():8.3f}")
    print(f"  largest hourly step  {steps.max():8.1f} kW")
    print(f"  99th pct hourly step {np.percentile(steps,99):8.1f} kW")
    print("\n  --- worst-case transient (DESIGN PARAMETER for SC sizing) ---")
    for d, m, k in top:
        print(f"    {m:<32s} {k*scale:6.1f} kW   ({d.split('+')[0].strip()})")
    print(f"    {'simultaneous step':<32s} {step_kw:6.1f} kW over "
          f"{TRANSIENT_DURATION_S:.0f} s")
    print(f"    {'energy to absorb':<32s} {step_kj:6.0f} kJ  <- sizes the SC bank")

    print("\n  --- share of campus energy by department ---")
    for k, v in sorted(cols.items(), key=lambda kv: -kv[1].sum()):
        print(f"    {k:<44s} {v.sum()/campus.sum()*100:5.1f} %")


if __name__ == "__main__":
    main()
