"""
Step 1 — Data preparation.

Reads the raw NASA POWER hourly CSV, cleans it, builds a synthetic load
profile, and writes one tidy file: data/inputs.csv

Output columns
    hour     0 .. 8759
    ghi      global horizontal irradiance, W/m^2
    tamb     ambient temperature, degC
    load_kw  load demand, kW

Run from the project root:
    python src/prepare_data.py
"""

import numpy as np
import pandas as pd

RAW_FILE = "data/nasa_power_raw.csv"
OUT_FILE = "data/inputs.csv"

# ----- load profile assumptions (change these to suit your site) -----
PEAK_LOAD_KW = 5.0      # evening peak
BASE_LOAD_KW = 1.0      # overnight baseline
NOISE_PCT = 0.10        # +/- random variation, hour to hour
RANDOM_SEED = 42


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
        raise ValueError(
            "Could not find the data header in the NASA file. "
            "Open it and check the download succeeded."
        )

    df = pd.read_csv(path, skiprows=start)
    df = df.rename(columns={"ALLSKY_SFC_SW_DWN": "ghi", "T2M": "tamb"})

    # NASA uses -999 for missing data
    df[["ghi", "tamb"]] = df[["ghi", "tamb"]].replace(-999.0, np.nan)
    df[["ghi", "tamb"]] = df[["ghi", "tamb"]].interpolate(limit_direction="both")

    df["ghi"] = df["ghi"].clip(lower=0.0)
    return df[["YEAR", "MO", "DY", "HR", "ghi", "tamb"]].reset_index(drop=True)


def daily_load_shape():
    """
    Relative demand for each hour of the day, 0.0 to 1.0.
    Low overnight, a morning bump, a dip midday, an evening peak.
    Edit these 24 numbers to match your own site.
    """
    shape = np.array([
        0.30, 0.28, 0.26, 0.26, 0.28, 0.35,   # 00-05
        0.50, 0.65, 0.70, 0.60, 0.55, 0.55,   # 06-11
        0.58, 0.60, 0.58, 0.60, 0.70, 0.85,   # 12-17
        1.00, 0.98, 0.90, 0.75, 0.55, 0.40,   # 18-23
    ])
    return shape


def build_load(n_hours, seed=RANDOM_SEED):
    rng = np.random.default_rng(seed)
    shape = daily_load_shape()

    days = int(np.ceil(n_hours / 24))
    profile = np.tile(shape, days)[:n_hours]

    load = BASE_LOAD_KW + (PEAK_LOAD_KW - BASE_LOAD_KW) * profile
    load *= 1.0 + rng.uniform(-NOISE_PCT, NOISE_PCT, size=n_hours)
    return np.clip(load, 0.0, None)


def main():
    df = read_nasa_power(RAW_FILE)
    n = len(df)
    print(f"Read {n} hourly rows from {RAW_FILE}")

    if n not in (8760, 8784):
        print(f"  warning: expected 8760 (or 8784 in a leap year), got {n}")

    out = pd.DataFrame({
        "hour": np.arange(n),
        "ghi": df["ghi"].to_numpy(),
        "tamb": df["tamb"].to_numpy(),
        "load_kw": build_load(n),
    })
    out.to_csv(OUT_FILE, index=False)

    # ---- sanity numbers: read these, do not skip them ----
    annual_ghi = out["ghi"].sum() / 1000.0          # kWh/m2/yr
    annual_load = out["load_kw"].sum()              # kWh/yr
    daylight = (out["ghi"] > 20).sum()

    print(f"\nWrote {OUT_FILE}")
    print(f"  annual irradiation   {annual_ghi:8.1f} kWh/m2   (expect ~1400-2000 in India)")
    print(f"  peak GHI             {out['ghi'].max():8.1f} W/m2    (expect ~900-1100)")
    print(f"  daylight hours       {daylight:8d} h       (expect ~4000-4500)")
    print(f"  mean temperature     {out['tamb'].mean():8.1f} degC")
    print(f"  annual demand        {annual_load:8.1f} kWh")
    print(f"  mean / peak load     {out['load_kw'].mean():.2f} / {out['load_kw'].max():.2f} kW")

    if out["ghi"].max() > 1400:
        print("  WARNING: peak irradiance is impossibly high, check the file")
    if annual_ghi < 800:
        print("  WARNING: annual irradiation looks too low, check the file")


if __name__ == "__main__":
    main()
