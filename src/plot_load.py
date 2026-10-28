"""
Load variation figures.

Produces four figures in figures/ :

  load_daily.png      average day, by season and by weekday/weekend
  load_heatmap.png    the whole year as hour-of-day vs day-of-year
  load_duration.png   load duration curve
  load_worst_week.png the week containing the worst generation deficit

Run from the project root:
    python src/plot_load.py
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from simulator import load_inputs, pv_output_kw, LPSP_TARGET

OUT = "figures"
SWEEP_CSV = "results/grid_sweep.csv"

INK = "#1C2529"
SLATE = "#4A5A62"
MUTE = "#8A979D"
ENERGY = "#C86A0A"
FLOW = "#1F7A72"
LINE = "#DCE3E5"

def optimal_pv_kw():
    """PV size of the cheapest feasible design from the grid sweep."""
    if not os.path.exists(SWEEP_CSV):
        raise FileNotFoundError(f"{SWEEP_CSV} not found - run src/grid_sweep.py first")
    df = pd.read_csv(SWEEP_CSV)
    feasible = df[df["lpsp"] <= LPSP_TARGET]
    return float(feasible.sort_values("npc").iloc[0]["pv_kw"])


PV_KW_FOR_COMPARISON = optimal_pv_kw()

MONTH_DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(LINE)
    ax.tick_params(colors=MUTE, labelsize=9)
    ax.yaxis.label.set_color(SLATE)
    ax.xaxis.label.set_color(SLATE)
    ax.title.set_color(INK)
    ax.grid(axis="y", color=LINE, lw=0.8, alpha=0.7)
    ax.set_axisbelow(True)


def get():
    d = load_inputs()
    n = d["n"]
    load = d["load"]
    hod = np.arange(n) % 24
    doy = np.arange(n) // 24
    month = np.repeat(np.arange(1, 13), MONTH_DAYS).repeat(24)[:n]
    # 1 Jan 2023 was a Sunday -> day index 0 is a Sunday
    dow = (doy + 6) % 7                      # 0 = Monday
    return d, load, hod, doy, month, dow


# ---------------------------------------------------------------
def fig_daily(load, hod, month, dow):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))

    seasons = {
        "Winter (Dec-Feb)": np.isin(month, [12, 1, 2]),
        "Pre-monsoon (Mar-May)": np.isin(month, [3, 4, 5]),
        "Monsoon (Jun-Sep)": np.isin(month, [6, 7, 8, 9]),
        "Post-monsoon (Oct-Nov)": np.isin(month, [10, 11]),
    }
    colors = [INK, ENERGY, FLOW, MUTE]
    for (name, mask), c in zip(seasons.items(), colors):
        prof = [load[mask & (hod == h)].mean() for h in range(24)]
        ax1.plot(range(24), prof, color=c, lw=2, label=name)
    ax1.set_xlabel("Hour of day")
    ax1.set_ylabel("Mean demand (kW)")
    ax1.set_title("Average day by season", fontsize=11, loc="left")
    ax1.set_xticks(range(0, 24, 4))
    ax1.legend(frameon=False, fontsize=8.5)
    style(ax1)

    wk = dow < 5
    for name, mask, c in [("Weekday", wk, FLOW), ("Weekend", ~wk, ENERGY)]:
        prof = [load[mask & (hod == h)].mean() for h in range(24)]
        ax2.plot(range(24), prof, color=c, lw=2.2, label=name)
    ax2.set_xlabel("Hour of day")
    ax2.set_ylabel("Mean demand (kW)")
    ax2.set_title("Weekday vs weekend", fontsize=11, loc="left")
    ax2.set_xticks(range(0, 24, 4))
    ax2.legend(frameon=False, fontsize=9)
    style(ax2)

    fig.tight_layout()
    fig.savefig(f"{OUT}/load_daily.png", dpi=150)
    plt.close(fig)

    gap = ([load[wk & (hod == h)].mean() for h in range(24)][14]
           - [load[~wk & (hod == h)].mean() for h in range(24)][14])
    print(f"  weekday-weekend gap at 14:00: {gap:.1f} kW")


# ---------------------------------------------------------------
def fig_heatmap(load, doy):
    days = doy.max() + 1
    grid = load[:days * 24].reshape(days, 24).T

    fig, ax = plt.subplots(figsize=(11, 4))
    im = ax.imshow(grid, aspect="auto", origin="lower", cmap="YlGnBu",
                   extent=[0, days, 0, 24])
    ax.set_ylabel("Hour of day")
    ax.set_yticks(range(0, 25, 4))
    cum = np.cumsum([0] + MONTH_DAYS)
    ax.set_xticks(cum[:-1] + np.array(MONTH_DAYS) / 2)
    ax.set_xticklabels(MONTH_NAMES)
    ax.set_title("Demand across the year  (kW)", fontsize=11, loc="left", color=INK)
    ax.tick_params(colors=MUTE, labelsize=9)
    cb = fig.colorbar(im, ax=ax, pad=0.015)
    cb.ax.tick_params(colors=MUTE, labelsize=8)
    cb.outline.set_edgecolor(LINE)

    fig.tight_layout()
    fig.savefig(f"{OUT}/load_heatmap.png", dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------
def fig_duration(load):
    srt = np.sort(load)[::-1]
    pct = np.arange(len(srt)) / len(srt) * 100

    fig, ax = plt.subplots(figsize=(8, 4.2))
    ax.plot(pct, srt, color=INK, lw=2)
    ax.fill_between(pct, srt, color=FLOW, alpha=0.12)

    peak, mean = srt[0], load.mean()
    ax.axhline(mean, color=ENERGY, lw=1.4, ls="--")
    ax.text(52, mean * 1.03, f"mean {mean:.0f} kW", color=ENERGY, fontsize=9)
    ax.text(1, peak * 0.97, f"peak {peak:.0f} kW", color=INK, fontsize=9, va="top")

    ax.set_xlabel("Percentage of the year demand is exceeded (%)")
    ax.set_ylabel("Demand (kW)")
    ax.set_title(f"Load duration curve   ·   load factor {mean/peak:.3f}",
                 fontsize=11, loc="left")
    ax.set_xlim(0, 100)
    style(ax)
    fig.tight_layout()
    fig.savefig(f"{OUT}/load_duration.png", dpi=150)
    plt.close(fig)

    for q in (1, 10, 50, 90):
        print(f"  demand exceeded {q:2d}% of the year: {np.percentile(load, 100-q):7.1f} kW")


# ---------------------------------------------------------------
def fig_worst_week(d, load):
    pv = pv_output_kw(PV_KW_FOR_COMPARISON, d["ghi"], d["tamb"])
    days = len(load) // 24
    daily_net = (pv[:days*24].reshape(days, 24).sum(1)
                 - load[:days*24].reshape(days, 24).sum(1))

    # worst run of consecutive deficit days
    worst = (0, 0, 0.0)
    run_len, run_start, run_sum = 0, 0, 0.0
    for i, v in enumerate(daily_net):
        if v < 0:
            if run_len == 0:
                run_start = i
            run_len += 1
            run_sum += v
            if run_sum < worst[2]:
                worst = (run_len, run_start, run_sum)
        else:
            run_len, run_sum = 0, 0.0

    wl, ws, wdef = worst
    if wl == 0:
        # no deficit day at all - fall back to the week of lowest generation
        wk = np.convolve(daily_net, np.ones(7), "valid")
        ws, wl, wdef = int(wk.argmin()), 7, float(wk.min())
        print("  no deficit days; showing the lowest-generation week instead")
    start = max(0, ws - 2)
    end = min(days, ws + wl + 2)
    sl = slice(start * 24, end * 24)
    t = np.arange(end - start) + start

    fig, ax = plt.subplots(figsize=(11, 4.2))
    hrs = np.arange(sl.stop - sl.start) / 24.0 + start
    ax.plot(hrs, load[sl], color=ENERGY, lw=1.8, label="Demand")
    ax.plot(hrs, pv[sl], color=FLOW, lw=1.8, label=f"PV output ({PV_KW_FOR_COMPARISON:,.0f} kW)")
    ax.axvspan(ws, ws + wl, color=INK, alpha=0.07)
    label = (f"{wl} deficit days\n{-wdef:,.0f} kWh short" if wdef < 0
             else f"lowest-generation week\n{wdef:,.0f} kWh net")
    ax.text(ws + wl / 2, ax.get_ylim()[1] * 0.93, label,
            ha="center", fontsize=9, color=INK)

    ax.set_xlabel("Day of year")
    ax.set_ylabel("Power (kW)")
    ax.set_title("The week that sizes the battery", fontsize=11, loc="left")
    ax.legend(frameon=False, fontsize=9)
    style(ax)
    fig.tight_layout()
    fig.savefig(f"{OUT}/load_worst_week.png", dpi=150)
    plt.close(fig)

    print(f"  worst deficit run: {wl} days from day {ws+1}, {-wdef:,.0f} kWh short")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    d, load, hod, doy, month, dow = get()
    print(f"Load: peak {load.max():.1f} kW, mean {load.mean():.1f} kW, "
          f"load factor {load.mean()/load.max():.3f}\n")
    fig_daily(load, hod, month, dow)
    fig_heatmap(load, doy)
    fig_duration(load)
    fig_worst_week(d, load)
    print(f"\n  four figures written to {OUT}/")
