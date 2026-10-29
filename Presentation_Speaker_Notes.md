# Speaker notes — Optimal Cost Sizing of a PV–Battery Microgrid for IIT Guwahati

34 slides. The same notes are in each slide's notes pane in `IITG_BTP_Microgrid_Presentation.pptx`.

## Slide 1 — Title

Introduce yourself, your supervisor and the project in one sentence: we size a solar plus battery system for two IIT Guwahati departments at the lowest 15-year cost while keeping unmet demand at or below 1 %, and then test how robust that answer is to weather, demand growth, grid access, a supercapacitor and uncertain inputs. Fill in the roll number and date before presenting, and place the IITG logo in the grey slot.

## Slide 2 — Outline of the talk

Walk through the structure. Part I sets up the problem, Part II positions it in the literature, Part III explains the model and optimiser, Part IV gives the optimal design and stress-tests it, and Part V covers the scenario studies and conclusions. The flow strip at the bottom is the logic of the whole project: data feed a verified simulator, an optimiser searches it, and the optimum is then tested against weather, uncertainty and alternative scenarios.

## Slide 3 — What is a microgrid?

A microgrid is a local group of generators, storage and loads that can be controlled as one unit and can either connect to the main grid or run islanded (Lasseter 2002; Hatziargyriou et al. 2007). Point out the common bus and the controller. Then the coupling choice: in an AC-coupled system each source has its own converter onto an AC bus; in a DC microgrid PV and batteries share a DC bus, which saves conversion stages (Dragičević et al. 2016). Be explicit that this project models an AC-coupled system, the same topology as the reference study: the PV inverter is inside the CERC all-in PV cost and the battery connects through a bidirectional converter. The off-grid case means islanded operation with no utility connection.

## Slide 4 — IIT Guwahati departmental electricity demand

The study supplies two departments: Mechanical Engineering with the Central Workshop, and Electronics and Electrical Engineering. Annual demand is 3,267 MWh with a 644 kW peak; the load factor (mean over peak) is 0.58. Mechanical plus Workshop is slightly larger. The load is not metered: it is built bottom-up from equipment inventories (rated kW, duty, operating hours), the weekday calendar and two vacation periods, then checked against the campus statistics in Kumar et al. Stress that this is the project's largest assumption and that demand turns out to be the strongest cost driver.

## Slide 5 — Solar resource and why storage is needed

NASA POWER hourly data for the campus point give 1,639 kWh/m² in 2023. Left: monthly sunshine; pre-monsoon months are sunniest and the monsoon brings dull spells. Right: the worst week. Every month has more PV energy than demand, so the shortfall is not seasonal: it comes from runs of consecutive dull days. In this week three deficit days add up to about 13.7 MWh short, which is what sizes the battery. Demand peaks in working hours while PV peaks at noon, and the evening and night load must come from storage.

## Slide 6 — Research motivation and objectives

The core tension: PV energy is cheap but intermittent; storage removes unmet demand but is expensive and wears out. The Pareto curve on the right, from the 2,700-design sweep, shows the price of reliability: each step towards zero unmet demand costs more. We fix the reliability target at LPSP ≤ 1 % of annual demand and minimise the 15-year net present cost, which includes replacements and salvage, not just capital. Decision variables are PV size, battery strings, converter rating, and supercapacitor strings.

## Slide 7 — Research landscape

A qualitative timeline of the work this project builds on, not a publication count. Borowy and Salameh (1996) sized PV and battery for a target loss-of-power-supply probability at minimum cost. Kennedy and Eberhart (1995) introduced particle swarm optimisation. Lasseter (2002) framed the microgrid concept. HOMER (Lambert et al. 2006) made hourly techno-economic simulation standard. Yang et al. (2008) combined LPSP with a genetic algorithm; Dufo-López and Bernal-Agustín (2008) went multi-objective. Dragičević et al. (2016) reviewed DC microgrids. Xu et al. (2018) modelled battery degradation from counted stress cycles. Kumar et al. (2018) applied HOMER to the IITG campus.

## Slide 8 — Reference study: Kumar et al. (2018), IEEE Access

Kumar et al. used HOMER Pro with its multi-year module for the whole IITG campus (peak 3,075 kW, about 60,379 kWh a day), with 10 % yearly load growth over 15 years, comparing 12 off-grid and grid-connected scenarios with PV, food-waste biogas, diesel and lead-acid batteries. Their best off-grid case (scenario 8, load following) had NPC ₹5,835 M and LCOE ₹11.96/kWh; grid-connected LCOE was ₹0.18–1.39/kWh. We take their costs, economics and battery choice; we change the scope (two departments), the tool (our own verified Python model), the battery ageing model, the optimiser and the robustness tests.

## Slide 9 — Critical literature comparison

Read across the rows. Each study covers part of the problem. Borowy and Salameh introduced LPSP-constrained least-cost sizing; Yang et al. solved it with a genetic algorithm; Dufo-López and Bernal-Agustín added emissions and unmet load as objectives; Xu et al. showed how to estimate battery life from counted stress cycles; Kumar et al. gave the site, costs and benchmark for IITG. This project combines LPSP-constrained NPC minimisation with cycle-counted ageing, multiple weather years and uncertainty analysis in one reproducible model. Only facts confirmed from the papers' records are in the table.

## Slide 10 — Research gap and contribution

Be careful with the claim. None of these techniques is new on its own. The gap is in combining them for this site, and in checking the assumptions a black-box tool hides. HOMER's default battery model treats lifetime throughput as constant regardless of depth of discharge; a single weather year can flatter a design; and the reference paper's inputs were never re-checked against their source. This project addresses each of these in an open, verified Python model.

## Slide 11 — Research questions, methods and answers

This map is the spine of the talk. Each question has a method, a script, an answer and the slide where the evidence is shown. Use it to signpost: every result later on answers one of these rows.

## Slide 12 — Proposed system architecture

The modelled system, AC-coupled as in Kumar et al. The PV array feeds the AC bus through its own inverter, whose cost is inside CERC's all-in PV price. The battery bank is 177 strings of 20 × 3 kWh batteries behind a bidirectional converter (efficiency 0.95). Each hour the dispatch is load following: PV serves the load first; surplus charges the battery within its current, converter and state-of-charge limits, and the rest is curtailed; a deficit is drawn from the battery and whatever it cannot supply is unmet demand. The supercapacitor (dashed) is an optional add-on studied separately; it does not take part in the hourly energy balance.

## Slide 13 — Demand and weather data pipeline

prepare_data.py builds the hourly demand: each department's equipment list gives rated kW, a duty factor and operating hours; a calendar applies weekdays and the two vacation periods (equipment runs at 45 % in vacation); the result is calibrated against the campus statistics and written to data/inputs.csv. NASA POWER supplies hourly irradiance (CERES SYN1deg) and temperature (MERRA-2). The same script writes the worst-case transient (four machines switching together: 93 kW for 5 s) for the supercapacitor study. The 2013–2024 weather years feed the robustness and Monte Carlo studies.

## Slide 14 — PV, battery and converter models

The PV model is equation 3 of Kumar et al.: rated capacity times a derating factor of 0.85 times irradiance over 1,000 W/m², corrected for cell temperature with a coefficient of −0.40 %/°C; cell temperature comes from ambient temperature and irradiance through the NOCT model with NOCT 45 °C. The battery is an energy bucket between 20 % and 100 % state of charge, with the 85 % round-trip efficiency split equally between charge and discharge. Charge and discharge are limited by the datasheet currents (57 A and 133.9 A at 12 V). The converter limits both directions to its rating and costs 5 % each way.

## Slide 15 — Reliability and lifecycle cost formulation

Reliability is LPSP: unmet energy over demand for the year, which must be at most 1 %. It is an energy measure, not a count of shortage hours. Economics follow HOMER's conventions. The real discount rate is (1.1070/1.0571) − 1 = 4.72 %. NPC adds capital, discounted replacements and O&M, and subtracts the discounted salvage value of life left at year 15. LCOE is NPC times the capital recovery factor (0.0945) divided by energy served. Battery life is the shorter of the wear life and the float life. Wear life comes from rainflow-counting the hourly state of charge and Miner's rule on the datasheet cycle-life curve; float life comes from the datasheet's service-life versus temperature curve averaged over the site's hourly temperatures: 12.1 years.

## Slide 16 — Mathematical optimisation formulation

Four decision variables: PV capacity, number of battery strings, converter rating and supercapacitor strings. Minimise NPC subject to LPSP ≤ 1 % and enough supercapacitor strings to absorb the 465 kJ transient (4 strings). Strings are integers. Constraints are folded into a feasibility-first score: a feasible design scores its NPC; an infeasible one scores 10¹⁰ × (1 + violation), so any feasible design beats any infeasible one and smaller violations rank better. A plain penalty NPC + k × violation can let a slightly unreliable but cheap design win. The supercapacitor count is fixed at the requirement in the final runs, because extra strings only add cost.

## Slide 17 — Python simulator and its verification

One function, simulate(), evaluates a design: it computes PV output for the year, steps through the 8,760 hours of dispatch, then computes battery life and the lifecycle cost and folds the constraints into the score. It runs in about 9 ms, which makes the 2,700-design sweep and PSO cheap. Verification means the code does what it is meant to: 35 automated checks pass. These cover physical limits, energy balances that close exactly, monotonic behaviour, hand calculations of LCOE, salvage, cycle life and float life, the penalty logic, and agreement of the 15-year model with the single-year model when there is no growth. Verification is not external validation: there is no measured microgrid to compare against, which is a stated limitation.

## Slide 18 — Grid search and particle swarm optimisation

The grid sweep tests 2,700 designs: 12 PV sizes from 1,500 to 7,000 kW, 25 battery sizes from 20 to 500 strings and 9 converter ratings from 600 to 2,200 kW. Its best feasible design costs ₹387.7 M. PSO uses 20 particles for 40 iterations with the Clerc–Kennedy constriction coefficients (w = 0.7298, c1 = c2 = 1.49618), velocity capped at 20 % of the range, absorbing walls, and positions rounded to whole kW and strings with a cache. Five independent seeds all finish within 0.41 % of each other and below the grid best, after about 820 simulations each. A fine local grid of 3,179 designs around the PSO answer finds nothing better. That is strong evidence of a good optimum, not a proof of global optimality.

## Slide 19 — Optimal off-grid sizing

The optimum is 4,368 kW of PV, 10.6 MWh of battery (177 strings), a 998 kW converter and the 4 required supercapacitor strings. NPC is ₹385.1 M, LCOE ₹11.25/kWh, LPSP exactly at the 1 % limit, and battery life 7.7 years, so the bank is replaced once within 15 years. PV capital is the largest item; battery capital plus its replacement is next. The balance: more PV is cheaper than more battery for covering most shortfalls, but PV alone cannot carry the night, and a bigger bank cycles less and lasts longer. The grid sweep's best was ₹387.7 M; PSO is 2.6 M cheaper because it searches between grid points.

## Slide 20 — Design space: a flat valley along the reliability boundary

Left: NPC over PV and battery size at a 1,000 kW converter; grey is infeasible (LPSP above 1 %), the black line is the 1 % boundary, and both optima sit on it. Right: along that boundary, more PV means less battery is needed, and NPC is flat over a wide range. 6 feasible grid designs lie within 2 % of the cheapest, and the five cheapest are within 1.6 %. Practically, that gives freedom to choose PV and battery sizes to suit roof area, procurement or phasing, at almost no cost penalty.

## Slide 21 — Energy flows and hourly dispatch

Left: a year at the optimum. PV generates about 5,593 MWh. About a third goes straight to the load, a third into the battery, and 1,920 MWh (34 %) is curtailed because the battery is full. Battery and converter losses are about 441 MWh. Unmet demand is 33 MWh, 1 % of demand. Right: the sunniest day, when the battery fills by mid-morning and PV is curtailed, and the worst day, when the battery is empty and demand goes unmet in the evening and night. High curtailment is the price of reliability in an islanded system.

## Slide 22 — Battery operation and ageing

Left: rainflow count of the hourly state of charge. Most cycles are 30–50 % deep, the daily charge and discharge. Feeding these depths through the datasheet cycle-life curve and Miner's rule gives a wear life of 7.7 years, shorter than the 12.1-year float life, so this bank is limited by cycling and is replaced once, in year 7.7. Right: bigger banks cycle shallower and last longer, until about 20 MWh where they hit the float-life ceiling. That is why lifecycle cost, not capital cost, decides the bank size: a cheaper small bank needs more replacements. Replacements cost ₹54.6 M in present value.

## Slide 23 — Multi-year weather robustness

The 2023-optimised design was run unchanged on 12 years of NASA weather, 2013–2024, with the 2023 load. It misses the 1 % target in 8 of 12 years; the worst is 2022 at 2.43 %. 2023 was the second-sunniest year in the record, which flatters the design. The robust design was explicitly optimised, not picked by trial: PSO (20 particles, 30 iterations, started from the 2023 optimum) minimised the mean NPC over the 12 years subject to LPSP ≤ 1 % in every year. It needs 5,246 kW PV and 11.8 MWh battery and costs ₹438 M on average, 14 % more. In 2023 itself the nominal design has 17 shortage events totalling 133 hours; the longest lasts 14 hours.

## Slide 24 — One-at-a-time sensitivity of the re-optimised cost

Each input is changed on its own, PSO re-optimises the design, and the plot shows the percentage change in the re-optimised NPC from the base. That is the cost of the best design under the new conditions, not of today's design. Demand dominates: ±20 % demand moves cost by about ±20 %, almost proportionally, because every component scales with it. PV price is next, then battery price and battery cycle life. The discount rate and converter price hardly matter. PV derating is limited to ±6 % so it stays physical.

## Slide 25 — The reliability target: what each step costs

Here the constraint itself is varied and the design re-optimised for each target. Going from 1 % to 0.1 % unmet demand raises NPC by 22 %; relaxing to 10 % cuts it by 28 %. The design changes too: tighter targets need much more battery, while PV changes less. The tornado chart in plot_results.py gives the same ranking as the spider plot. The practical point: the 1 % target is a choice with a price, and should be agreed with the institute, for example by exempting loads that can be shed.

## Slide 26 — Monte Carlo uncertainty analysis

Sensitivity moves one input at a time; this moves all of them at once. 1,000 samples, design fixed at the optimum. Prices of PV, battery and converter, the real discount rate and battery cycle life are uniform within ±20 %; PV derating within ±6 %; demand within ±10 %; and the weather year is drawn uniformly from 2013–2024. 90 % of sampled NPCs fall between ₹343 M and ₹436 M: this is the 5th to 95th percentile of the sampled outcomes, not a statistical confidence interval. The design misses the 1 % target in 60 % of samples. The right panel shows that prices and cycle life drive cost, while demand and weather drive reliability.

## Slide 27 — Load growth and staged expansion

With demand growing 10 % a year (Kumar et al.), year-15 demand is 3.8 times year 1, and today's optimum fails from year 2. Two strategies, both meeting 1 % in every year: build everything for year 15 at the start, or add capacity at the start of years 1, 6 and 11. Each is optimised with PSO plus a local search and two seeds, which agree within 0.12 %. Staging costs ₹880 M against ₹1,305 M, 33 % less. Two effects: money spent later is discounted, and the early oversized battery in the build-once plan cycles shallowly for years and still ages. The staged LCOE of ₹13.08/kWh lies inside the paper's off-grid range of ₹11.96–18.47/kWh.

## Slide 28 — Grid-connected alternatives

With a grid at the Assam commercial tariff of ₹5.96/kWh, buying everything costs ₹206 M. Adding 2,400 kW of PV cuts this to ₹142 M (₹4.11/kWh), the cheapest option overall, because PV's lifetime cost is about ₹4.3/kWh, below the tariff. Exports are paid at the tariff, as the paper assumes, but capped at the 644 kW peak load: without a cap more PV would always look profitable. The battery never pays: every MWh adds cost, even with no export payment, because storing a kWh in lead-acid costs more than buying one. Important: the grid is assumed always available, so this is not the same reliability boundary as off-grid; outages are not modelled.

## Slide 29 — Supercapacitor: what it would see

The hourly model cannot see a supercapacitor. sc_study.py builds a synthetic 1-second load for a working hour from the equipment list: machines switch on and off as Markov chains, direct-on-line motors draw a starting surge, and welders flicker. Left: one 30-minute window at 1 s, 1 min and 1 h. Right: a first-order low-pass filter with time constant τ sends the slow part of the storage power to the battery and the fast part to the supercapacitor. The design transient is 93 kW for 5 s, 465 kJ, needing 4 strings of 24 modules (16 V, 58 F). For this 10.6 MWh bank that step is only 0.0088 C, far below the C/10 rate the battery is rated at.

## Slide 30 — Is a supercapacitor economically justified?

Its only economic value here is longer battery life. sc_study.py rainflow-counts the battery's second-scale cycles with and without the supercapacitor, adds them to the hourly cycles, and converts the life gain into NPC saved. Those cycles are far shallower than the datasheet's lowest point (20 % DoD), so two bounds are used: extending the datasheet's log-log slope (upper) or constant wear per kWh (lower). At τ = 1 s the SC and its DC–DC stage cost ₹2.59 M and save ₹0.05–2.60 M; at τ = 2 s ₹3.82 M against ₹0.07–3.60 M. At best it breaks even; longer filters cost more than they save. A smaller bank saves fewer rupees, not more, because it is cheaper to replace. Technical benefit is not economic benefit, and several inputs are placeholders.

## Slide 31 — Checking the reference paper against CERC

Kumar et al. cite the CERC FY 2016-17 tariff order (Petition SM/03/2016, 29 April 2016) for the PV cost and discount rate. The order says ₹530.02 lakh/MW, which is ₹53,002/kW, and a discount factor of 10.64 % (12.76 % × 0.70 × (1 − 34.61 %) + 16 % × 0.30). The paper uses ₹50,502/kW and 10.70 %. 10.70 % is the earlier figure that the order replaces; 50,502 does not appear in the order. We do not speculate about why. Re-running with the CERC values raises NPC by 2.3 % to ₹393.9 M, and re-optimising returns the same design. We keep the paper's values as the base case for comparability and report the corrected case. The lesson for reproducibility: check inputs against the primary source, not the citing paper.

## Slide 32 — Integrated engineering discussion

Pull the threads together. Cost is set mostly by demand and the PV and battery prices. Reliability is set by weather and demand, and a single-year optimum sits exactly on the 1 % boundary, so any worse year breaks it. Robustness costs about 14 % for weather alone. Growth favours staging. Grid access changes the answer completely. The supercapacitor's case is conditional. The central message: optimal sizing is a trade-off between lifecycle cost, reliability and robustness, and the cheapest nominal design is the least robust one.

## Slide 33 — Conclusions, limitations and future work

Conclusions are the verified numbers. Limitations are stated plainly: the load is synthetic, the model is verified but not validated against a measured system, the supercapacitor inputs are placeholders, the battery costs date from 2016, and the grid case ignores outages. Future work follows directly from the limitations: meter data, a multi-year design as the headline result, LFP batteries, diesel backup as in the reference study, CO₂ accounting and real supercapacitor quotes.

## Slide 34 — References and acknowledgements

Point to the full list in References.md and resources/SOURCES.md. Thank your supervisor, Kuldeep Kumar, the Department of Energy Engineering, and the providers of open data (NASA POWER) and the reference study. Then invite questions.

