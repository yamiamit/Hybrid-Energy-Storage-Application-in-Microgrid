# Presentation QA report

Deck: `IITG_BTP_Microgrid_Presentation.pptx` (and `.pdf`). Built 29 October 2026.

## 1. Slide count

**34 slides**, within the 28–34 target. 34 of 34 have speaker notes, and the same notes are in `Presentation_Speaker_Notes.md`.

| Part | Slides |
|---|---|
| I Introduction | 1 Title · 2 Outline · 3 What is a microgrid · 4 Departmental demand · 5 Solar resource · 6 Motivation and objectives |
| II Literature and gap | 7 Research landscape · 8 Reference study · 9 Literature comparison · 10 Gap and contribution · 11 Research questions map |
| III Modelling | 12 Architecture · 13 Data pipeline · 14 Component models · 15 Reliability and cost · 16 Optimisation formulation · 17 Simulator and verification · 18 Grid search and PSO |
| IV Results and robustness | 19 Optimal sizing · 20 Design space · 21 Energy flows · 22 Battery ageing · 23 Weather robustness · 24 Sensitivity · 25 Reliability target · 26 Monte Carlo |
| V Scenarios and conclusions | 27 Load growth · 28 Grid-connected · 29 Supercapacitor (what it sees) · 30 Supercapacitor (economics) · 31 CERC check · 32 Discussion · 33 Conclusions · 34 References |

## 2. Template identification and preservation

- **Template used:** `Hybrid Energy Storage Application in Microgrid — BTP Final Presentation.pptx` in the project root.
  - It is the only local deck with IIT Guwahati branding: the institute name and the Department of Energy Engineering on the title slide.
  - It has a navy header band with an amber rule, an eyebrow and title, a logo slot, and a footer with page numbers.
  - It names Amit Raj and the supervisor, Kuldeep Kumar.
  - Its slides held placeholder content from an earlier plan (HESS Cases A/B/C, an XGBoost surrogate, a 20-year horizon). That content was **not** reused.
- **Other deck found:** `resources/BTP_Progress_Review.pptx` is the earlier progress review. It was made with PptxGenJS on the stock Office theme, so it is not the template.
- **What was preserved:**
  - The template's own theme (IBM Plex Sans for headings and body), slide master and layouts. The deck is a copy of the template file with its 30 placeholder slides removed.
  - The template's slide chrome is redrawn on every slide at the template's exact geometry and colours: navy `13233A`, amber `E8A33D`, steel `2E6F95`, card `FBFBF8`, border `D5DBE1`.
  - Slide size is 13.33 × 7.5 in, the same as the template.
- **Original not overwritten:** the template's MD5 (`cc2386c5…2512`) and timestamp (29 Oct, 11:09) are unchanged after the build.
- **No IITG logo exists in the template.** It has only empty logo slots: a white circle in each header and a grey circle on the title slide. They are kept as they are. **Insert the official logo before presenting.**
- **Font:**
  - The template's font is IBM Plex Sans, which is free under the SIL Open Font License. **Install it on the presenting computer.** Otherwise PowerPoint substitutes another font and text may reflow.
  - The PDF was exported with IBM Plex Sans embedded.

## 3. File and visual checks performed

- `validate.py --original <template>`: **all validations passed** (schema, relationships, content types, slides).
- **Visual review:** all 34 slides were rendered and inspected twice, first in a substitute font and then in IBM Plex Sans.
  - Fixed in the first review:
    - slide 6: caption overlapping the Objective box
    - slide 12: heading wrapping onto step 1
    - slide 13: arrow crossing a box
    - slide 17: text overflowing its card
    - slide 30: card clipped by the takeaway strip, with inaccurate wording
  - The final render showed no overflow, clipping or overlap.
- **Leftover-placeholder scan:** only the two deliberate fields remain, "Roll No. [add before presenting]" and "[Presentation date]" on slide 1.
- **Alt text:** every project figure carries a description.
- **Editable content:** diagrams and flowcharts on slides 2, 3, 7, 12, 13, 16, 17 and 18 are native PowerPoint shapes. Tables are native tables. Equations are editable text.

## 4. Figures used

All figures are the project's own PNGs from `figures/`, used unmodified. No new chart images were generated. Diagrams are drawn as shapes.

| Slide | Figures |
|---|---|
| 4 | load_departments |
| 5 | solar_resource, load_worst_week |
| 6 | pareto |
| 13 | load_heatmap |
| 18 | pso_convergence |
| 19 | cost_breakdown |
| 20 | npc_landscape, tradeoff |
| 21 | energy_flows, dispatch_days |
| 22 | soc_cycles, battery_life |
| 23 | perf_weather_years |
| 24 | sens_spider |
| 25 | sens_reliability |
| 26 | sens_montecarlo |
| 27 | growth_npc, growth_capacity |
| 28 | grid_scenarios, grid_battery |
| 29 | sc_resolution, sc_power_split |
| 30 | sc_payback |

Not used, but available as backup slides for questions: tornado, sens_twoway, perf_shortages, perf_battery, perf_pv, perf_scenarios, growth_spending, growth_lpsp, grid_feedin, grid_dispatch, sc_sizing, sc_battery_relief, sc_crate, pso_swarm, lpsp_landscape, converter_effect, curtailment, soc_year, monthly_supply, monthly_balance, load_daily, load_duration.

## 5. Numerical results: verification

Every project number on the slides is read from `presentation_assets/results.json`. `collect_results.py` wrote that file from the saved results in `results/` and from direct calls to the model. The checks below were run on 29 October.

| Claim | Value on slides | Source | Status |
|---|---|---|---|
| Annual demand, peak, load factor | 3,267 MWh, 644 kW, 0.58 | `data/inputs.csv` | Verified |
| Department split | 1,702 MWh (52 %) Mech + Workshop, 1,565 MWh (48 %) Elec | `data/inputs.csv` | Verified |
| Irradiation 2023 | 1,639 kWh/m² | `data/inputs.csv` | Verified |
| Optimum | 4,368 kW PV, 177 strings (10.6 MWh), 998 kW converter, 4 SC strings | `results/pso_runs.csv` + `simulate()` | Verified |
| NPC, LCOE, LPSP, battery life | ₹385.1 M, ₹11.25/kWh, 1.00 %, 7.7 y (one replacement, year 7.7) | `simulate(full=True)` | Verified |
| Grid sweep | 2,700 designs, best ₹387.7 M (4,000 kW, 13.2 MWh, 1,000 kW) | `results/grid_sweep.csv` | Verified |
| PSO repeatability | 5 of 5 feasible, spread 0.41 %, about 820 evaluations per run | `results/pso_runs.csv` | Verified |
| Verification checks | 20 simulator + 7 multi-year + 8 grid = **35, all passing** | re-run 29 Oct | Verified |
| Growth at 10 %/yr | build once ₹1,305.0 M, staged ₹880.1 M, **32.6 %** saving (shown as 33 %), staged LCOE ₹13.08 | `results/multiyear.csv` | Verified |
| Grid scenarios | grid only ₹206.0 M; grid + 2,400 kW PV ₹142.0 M, ₹4.11/kWh; battery 0 | `results/grid_connected.csv` + model | Verified |
| Weather years | misses 1 % in 8 of 12 years; worst 2.43 % (2022); robust design 5,246 kW / 196 strings (11.8 MWh) / 1,235 kW; mean NPC ₹438.2 M vs ₹385.4 M (+13.7 %, shown as 14 %) | `results/performance_weather.csv` | Verified |
| 2023 shortages | 133 h in 17 events, longest 14 h, median 9 h | `simulate()` unmet series | Verified |
| Spider sensitivities | demand −19.2 / +19.7 %; PV −9.3 / +9.0 %; battery −6.8 / +6.7 %; cycle life +7.3 / −4.3 % | `results/sens_spider.csv` | Verified |
| Reliability target | 0.1 % → +21.8 % (₹468.9 M); 10 % → −27.6 % (₹279.0 M) | `results/sens_reliability.csv` | Verified |
| Monte Carlo | 1,000 samples; 5th–95th percentile ₹342.8–435.8 M; target missed in 60.1 % | `results/montecarlo.csv` | Verified |
| Supercapacitor | step 93 kW for 5 s = 465 kJ; 93 / 10,620 kWh = **0.0088 C**; τ = 1 s: cost ₹2.59 M, saved ₹0.05–2.60 M; τ = 2 s: ₹3.82 M vs ₹0.07–3.60 M | `transient_spec.csv`, `sc_sizing.csv`, `sc_study.sc_saving()` | Verified |
| CERC-corrected NPC | ₹393.9 M (**+2.29 %**) at the optimum design | `simulate()` with CERC inputs | Verified |

### How each reported figure is defined

These matter if an examiner asks:

- **Sensitivity %:** the change in the *re-optimised* NPC relative to the base, with PSO re-run for each point. It is not the change in today's design's cost.
- **Monte Carlo range:** the 5th–95th percentile of sampled outcomes, not a confidence interval. Inputs are uniform within ±20 % (PV, battery and converter prices, real discount rate, cycle life), ±6 % (derating) and ±10 % (demand), and the weather year is uniform over 2013–2024. The design is fixed at the optimum.
- **Robust design:** explicitly optimised, not picked by testing. PSO with 20 particles and 30 iterations, warm-started from the 2023 optimum, minimised the mean NPC over the 12 years subject to LPSP ≤ 1 % in every year (`performance.robust_design`).
- **C-rate:** step power (kW) divided by nominal bank energy (kWh).
- **LPSP:** energy not served divided by demand over the year. Shortage hours are reported separately (133 h).

### Corrections relative to the brief

- **Battery model:** the exact designation is **12VRE-3000TF-L** (the Discover datasheet of 12 Nov 2013).
- **Microgrid topology:** the brief describes a "DC microgrid", but **the model is AC-coupled**: PV through its own inverter and the battery through a bidirectional converter onto an AC bus, as in Kumar et al. Slide 3 explains AC and DC coupling, and slides 3 and 12 state that this project is AC-coupled.
- **"Design unchanged" with CERC values:** this is based on a PSO re-optimisation run during the 28 Oct session (seed 2), which returned the same sizes (4,368 kW, 10,620 kWh) at ₹393.9 M. `collect_results.py` re-computes the NPC at the fixed design, not the re-optimisation.

## 6. Code execution status

- **Run on 29 Oct while making the deck:**
  - the three verification suites
  - `presentation_assets/collect_results.py`, which calls `simulate`, `compute_npc`, the grid model and `sc_study.sc_saving`
  - `presentation_assets/build_deck.py`
- **Reused from saved results, not re-run on 29 Oct** because they take 10–40 minutes:
  - `grid_sweep.csv` and `pso_runs.csv` (28 Oct, after the SC-pinning fix)
  - `multiyear.csv` (28 Oct, 2 seeds with warm starts)
  - `grid_connected.csv` (28 Oct)
  - `performance_weather.csv`, `sens_*.csv` and `montecarlo.csv` (29 Oct)
  - All were produced by the current code.
- **The scientific model was not modified** for the presentation. The presentation code is separate, in `presentation_assets/`.
- **To rebuild:**
  ```
  PYTHONPATH=src venv/bin/python presentation_assets/collect_results.py
  <python with python-pptx> presentation_assets/build_deck.py
  ```
  python-pptx is not in the project's venv; it was installed in a separate scratch environment.

## 7. Source verification status

| Source | How it was checked |
|---|---|
| Kumar et al. 2018 | Local PDF text checked. Off-grid NPC ₹5,835–9,009 M (load following); best scenario 8 at ₹5,835 M and ₹11.96/kWh; grid-connected LCOE ₹0.18–1.39/kWh; campus peak 3,075 kW and 60,379 kWh/day; HOMER Pro multi-year. |
| CERC SM/03/2016 and 17/SM/2015 | Local PDFs read: ₹530.02 lakh/MW (para 27; SO17 breakdown) and discount factor 10.64 % (para 9). |
| Discover datasheet (2013) | Local PDF read: cycle life 5,000 / 2,500 / 1,500 cycles; service-life graph. |
| Borowy & Salameh 1996; Yang et al. 2008; Dufo-López & Bernal-Agustín 2008; Xu et al. 2018 | Index and publisher records checked for authors, venue, DOI and stated method. The literature table states only what those records confirm. For Xu et al. the records confirm "cycle counting", not specifically rainflow, so the slide says "cycle counting". |
| Lasseter 2002; Hatziargyriou et al. 2007; Dragičević et al. 2016; Lambert et al. 2006 | DOIs and venues confirmed. The HOMER chapter is dated 2006 by NREL and OSTI, and 2005 in some lists. |
| Kennedy & Eberhart 1995; Clerc & Kennedy 2002; Miner 1945; ASTM E1049-85 | Standard references; Clerc & Kennedy also checked in the earlier session. Only bibliographic details are cited. |

The research-landscape slide (7) is a **qualitative timeline of cited milestones**. It contains no publication counts.

## 8. Unresolved assumptions and limitations

Each of these is shown on the slides.

- **Before presenting:**
  - Add your roll number and the presentation date (slide 1).
  - Insert the IITG logo into the logo slots.
  - Install IBM Plex Sans on the presenting computer.
- **Model placeholders:** supercapacitor module price (₹45,000), motor starting surge (5×), machine on-times, and equipment power ratings (slides 13 and 30).
- **Demand:** the load is synthetic (bottom-up from equipment), not metered (slides 4, 13 and 33).
- **Verification only:** the model passes 35 internal checks but has not been validated against a measured system (slides 17 and 33).
- **Grid case:** assumes the grid is always available, so it does not sit on the same reliability boundary as the off-grid case (slide 28).
- **Costs:** taken from 2016–17 (CERC and Kumar et al.); only lead-acid batteries are modelled (slide 33).
- **Base case kept on the paper's inputs:** the deck uses the paper's ₹50,502/kW and 10.70 % for comparability, and the CERC-corrected case is reported separately (slide 31).

## 9. Repository state

- **Nothing committed and nothing reset.** The template and all uncommitted research work are untouched.
- **New files:**
  - `IITG_BTP_Microgrid_Presentation.pptx` and `.pdf`
  - `Presentation_Speaker_Notes.md`, `References.md`, `Presentation_QA.md`
  - `presentation_assets/` (`collect_results.py`, `build_deck.py`, `results.json`)
- **Note:** `.gitignore` now lists `resources/`. That change was made outside this task and was left as is.
