# Sources

Every source the project uses, what was taken from it, and where it's used in the code.
Files marked **local** are in this folder or in `data/`. BibTeX entries for the thesis are in `references.bib`.

## Primary reference

**[1] A. Kumar, A. R. Singh, Y. Deng, X. He, P. Kumar, R. C. Bansal**, "Multiyear Load Growth Based Techno-Financial Evaluation of a Microgrid for an Academic Institution," *IEEE Access*, vol. 6, pp. 37533–37555, 2018. DOI: [10.1109/ACCESS.2018.2849411](https://doi.org/10.1109/ACCESS.2018.2849411)
- **Local:** `Multiyear_Load_Growth_Based_Techno-Financial_Evaluation_of_a_Microgrid_for_an_Academic_Institution.pdf`
- **Used for:**
  - Table 2: component costs for PV, battery and converter.
  - Section IV-C: inflation 5.71%, discount rate 10.70%, project life 15 years, fixed O&M ₹5 lakh per year, 10% load growth.
  - Section IV-B: the battery model (Discover 12VRE-3000TF-L, strings of 20, minimum SoC 20%).
  - Eq. (3): the PV output model.
  - Campus load figures used for calibration (peak 3,075 kW, load factor 0.82).
  - Table 4: benchmark NPC and LCOE.
- **Code:** `src/costs.py`, `src/prepare_data.py`, `src/simulator.py`

**[2] Central Electricity Regulatory Commission (CERC)**, *Determination of levellised generic tariff for FY 2016-17 under Regulation 8 of the CERC (Terms and Conditions for Tariff determination from Renewable Energy Sources) Regulations, 2012*, Petition No. SM/03/2016 (Suo-Motu), order dated 29 April 2016, New Delhi. https://cercind.gov.in/2016/orders/SORE.pdf
- **Local:** `CERC_levellised_generic_tariff_FY2016-17_SM-03-2016.pdf`
- This is reference [101] in [1].
- **Used for:** the PV benchmark cost and the discount rate, both taken through [1].

**[2a] Central Electricity Regulatory Commission (CERC)**, *Determination of Benchmark Capital Cost Norm for Solar PV power projects and Solar Thermal power projects applicable during FY 2016-17*, Petition No. 17/SM/2015, order dated 23 March 2016, New Delhi. https://cercind.gov.in/2016/orders/SO17.pdf
- **Local:** `CERC_solar_PV_capital_cost_FY2016-17_17-SM-2015.pdf`
- **Used for:** the breakdown behind the PV benchmark cost. It includes modules, civil works, mounting, the inverter (power conditioning unit) and evacuation; land is excluded.

### ⚠ The paper misquotes its CERC source

| | [1] says, and the code uses | [2] actually says |
|---|---|---|
| PV capital cost | ₹50,502/kW | **₹53,002/kW** (₹530.02 lakh/MW, [2] para 27 and [2a]) |
| Discount factor | 10.70% | **10.64%** ([2] para 9: 12.76% × 0.70 × (1 − 34.61%) + 16% × 0.30) |

₹50,502 appears nowhere in either order; it looks like a typo for ₹53,002. 10.70% was the earlier figure, which [2] replaces ("from 10.70% to 10.64%").

**Effect on this project:** with both CERC values, NPC rises **2.3%** (₹385.1 M → ₹393.9 M) and the optimal design is **unchanged**.

The code keeps the paper's values, so the results can be compared with [1] directly. State the discrepancy in the thesis.

## Site data

**[3] NASA POWER Project**, hourly data for 1 Jan to 31 Dec 2023, local solar time. https://power.larc.nasa.gov/
- **Local:** `data/nasa_power_raw.csv`
- **Location:** latitude 26.162, longitude 91.7668 (IIT Guwahati).
- **Parameters:**
  - `ALLSKY_SFC_SW_DWN`: global horizontal irradiance (CERES SYN1deg).
  - `T2M`: air temperature at 2 m (MERRA-2).
- **Used for:** PV output, and the hourly temperature behind the battery's float life.
- **Code:** `src/prepare_data.py` → `data/inputs.csv`
- **More weather years:** the same point and parameters for 2013–2024 are saved in `data/nasa_power_years/`.
  - Downloaded 29 October 2026 from the POWER hourly API.
  - The 2023 copy matches `data/nasa_power_raw.csv` exactly.
  - Used by `src/performance.py` and `src/sensitivity.py` to test the design in other weather years.

**[4] IIT Guwahati public web pages**, used for the equipment list in the bottom-up load model (`src/prepare_data.py`). Checked 28 October 2026.
- **Central Workshop:** https://iitg.ac.in/mech/workshop/
  - Lists the welding, fitting, foundry, carpentry, machine, CNC and turning shops.
  - The CNC shop has a CNC lathe, CNC milling, wire-cut EDM and die-sinking EDM.
- **ME110 Workshop-I syllabus:** https://www.iitg.ac.in/cse/ME110
  - Gas, TIG, MAG and submerged arc welding.
  - Shielded metal arc welding exercises.
  - Foundry melting and pouring.
- **Central Instruments Facility:** https://www.iitg.ac.in/cif/instruments.php and https://www.iitg.ac.in/iitg_academic?aca=central-instruments-facility
  - 26 analytical instruments, used by 11 of the 14 departments.
  - Includes a 400 MHz NMR and a scanning electron microscope.
- **Note:** none of these pages give power ratings. The kW figures in `prepare_data.py` are engineering estimates (see the placeholder table below).

## Battery datasheets

**[5] Discover Energy Corp.**, *12VRE-3000TF-L Tubular Flooded RE Series* datasheet, updated 12 Nov 2013. This is the exact model used in [1].
- **Local:** `Discover_12VRE-3000TF-L_datasheet_2013.pdf`
- **Online copy:** https://www.mrsolar.com/content/pdf/Discover/3000TF-L.pdf
- **Used for:**
  - **Cycle life:** 5,000 cycles at 20% depth of discharge, 2,500 at 50%, 1,500 at 80% (page 1 table; page 2 graph agrees).
  - **Service life against temperature:** 18 years at 20°C, falling with heat (page 2 graph, 12 V blocks). I read the lower edge of the band off the graph by eye.
  - **Internal resistance:** 5 mΩ.
  - **Capacity:** 3.0 kWh at the 120 h rate.
- **Code:** `src/costs.py` (`cycle_life`, `service_life`, `internal_resistance_ohm`) → `src/simulator.py`

**[6] Discover Energy Corp.**, *12VRE-3000TF Tubular Flooded OPzS* datasheet, updated 7 May 2018.
- **Local:** `Discover_12VRE-3000TF_OPzS_datasheet_2018.pdf`
- **Online copy:** https://shop.frankensolar.ca/content/documentation/Discover%20Energy/Datasheet_Discover_Energy_12VRE-3000TF_(frankensolar).pdf
- **Used for:** the pessimistic cycle-life case (4,500 / 2,000 / 1,100 cycles at 20 / 50 / 80% depth of discharge).
- **Code:** `src/costs.py` (`cycle_life_later_sheet`)

**[7] Canadian Battery Store**, product listing "Discover Energy SOPzS 12VRE-3000TF-L". https://canadianbatterystore.ca/product/discover-energy-sopzs-12vre-3000tf-l/
- **Used for:** a cross-check only. It quotes the same figures as [6] and isn't cited in the thesis.

## Methods

**[8] M. Clerc and J. Kennedy**, "The particle swarm — explosion, stability, and convergence in a multidimensional complex space," *IEEE Transactions on Evolutionary Computation*, vol. 6, no. 1, pp. 58–73, 2002. DOI: [10.1109/4235.985692](https://doi.org/10.1109/4235.985692)
- **Used for:** the PSO coefficients w = 0.7298 and c1 = c2 = 1.49618.
- **Code:** `src/pso.py`

**[9] M. A. Miner**, "Cumulative damage in fatigue," *Journal of Applied Mechanics*, vol. 12, pp. A159–A164, 1945.
- **Used for:** Miner's rule, under which each cycle of depth D uses up 1/N(D) of the battery's life.
- **Code:** `src/simulator.py` (`cycle_damage`), `src/sc_study.py`

**[10] ASTM E1049-85**, *Standard Practices for Cycle Counting in Fatigue Analysis*, ASTM International.
- **Used for:** rainflow cycle counting of the battery state of charge.
- **Implementation:** the Python package `rainflow` 3.2.0 (https://pypi.org/project/rainflow/), which implements this standard.
- **Code:** `src/simulator.py`, `src/plot_results.py`, `src/sc_study.py`

**[11] HOMER Pro** online documentation, UL Solutions / HOMER Energy. Checked 28 October 2026:
- **Salvage value:** https://homerenergy.com/products/pro/docs/latest/salvage_value.html
  - Linear depreciation based on replacement cost; example: 5/25 of life left gives 5/25 of the cost back.
- **Real discount rate, CRF, NPC:**
  - https://homerenergy.com/products/pro/docs/latest/economics.html
  - https://homerenergy.com/products/pro/docs/latest/total_annualized_cost.html
  - https://homerenergy.com/products/pro/docs/3.15/net_present_cost.html
- **LCOE:** https://support.homerenergy.com/docs/results/calculations/levelized-cost-of-energy
- **Lifetime throughput and battery life:**
  - https://homerenergy.com/products/pro/docs/latest/battery_bank_life.html
  - https://homerenergy.com/products/pro/docs/latest/kinetic_model.html
  - https://homerenergy.com/docs/knowledgebase/article/storage-faqs/
  - HOMER treats throughput as constant, independent of depth of discharge. Our rainflow model removes that limitation.
- **Used for:**
  - Discounting at the real rate: (1.1070 / 1.0571) − 1 = 4.72%.
  - Salvage value: last unit bought × fraction of life remaining.
  - LCOE = NPC × CRF / energy served.
  - The throughput battery model, kept for comparison.
- **Code:** `src/simulator.py`

## Placeholders with no source yet

Each of these must be sourced or labelled as an assumption in the thesis.

| Value | Current number | Where |
|---|---|---|
| Supercapacitor module price | ₹45,000 per 16 V / 58 F module | `simulator.py` `SC_PRICE_PER_MODULE_PLACEHOLDER` |
| Supercapacitor ESR and efficiency | none / 97% | `costs.py` `SUPERCAP` |
| SC DC-DC converter price | ₹10,000/kW (borrowed from the battery converter) | `sc_study.py` `DCDC_INR_PER_KW` |
| Motor starting surge | 5× rated power, 0.7 s decay | `sc_study.py` |
| Machine on-times | 25 s to 900 s per machine | `sc_study.py` `MEAN_ON_S` |
| Equipment power ratings | engineering estimates | `prepare_data.py` |
| Converter efficiency and life | 95%, 15 years | `costs.py` `CONVERTER` |
| PV life, derating, temperature coefficient | 25 years, 0.85, −0.40%/°C | `costs.py` `PV` |
| Battery room temperature | same as outdoor air | `simulator.py` `BATT_ROOM_OFFSET_C` |
