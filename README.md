# ⛽ Filling Up at the Right Price?

**A Streamlit data-storytelling app** on fuel prices in France.
StApp26 project — EFREI Paris, Business Intelligence & Analytics major.

> **Question:** *Does where you fill up really make a difference?*
> **Short answer:** yes. The price gap between stations of the same department is about
> **4 times larger** than the gap between departments.

---

## 1. Data

| | |
|---|---|
| **Dataset** | Prix des carburants en France – Flux instantané – v2 (Fuel prices in France – real-time feed) |
| **Portal** | data.gouv.fr (approved portal) |
| **Link** | https://www.data.gouv.fr/fr/datasets/6407d088d4e23dc662022e2c |
| **CSV export** | https://data.economie.gouv.fr/explore/dataset/prix-des-carburants-en-france-flux-instantane-v2/ |
| **Publisher** | French Ministry of the Economy and Finance (mandatory reporting by fuel stations) |
| **Licence** | Licence Ouverte / Etalab 2.0 |
| **File used** | `data/raw/prix-des-carburants-en-france-flux-instantane-v2.csv` (`;` separator) |
| **Snapshot** | 24 October 2026 — 9,819 stations, 47 columns |
| **Dimensions** | geographic (lat/lon, municipality, department, region) + road type + 6 fuels |

The feed is updated continuously. To reproduce with fresh data, download the CSV again from the link above
and re-run `prepare_data.py`.

## 2. Project structure

```
├── app.py                 # Streamlit app (narrative + visualisations)
├── prepare_data.py        # cleaning / validation -> clean files
├── requirements.txt
├── .streamlit/config.toml
├── README.md
├── VIDEO_SCRIPT.md        # outline of the 3-minute demo video
└── data/
    ├── raw/prix-des-carburants-en-france-flux-instantane-v2.csv   # raw data
    ├── stations_clean.csv     # one row per station (generated)
    ├── prices_long.csv        # one row per (station, fuel) (generated)
    └── quality_report.json    # cleaning figures, displayed in the app (generated)
```

## 3. Running the app

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python prepare_data.py        # optional: the clean files are already included
streamlit run app.py
```

**Deployment (Streamlit Community Cloud):** the GitHub repository contains the code only. On first start,
if `data/` is empty, the app runs `prepare_data.py`, which downloads the latest snapshot of the same dataset from
the official API (data.economie.gouv.fr) and cleans it. The online version therefore shows the most recent prices,
while the submitted zip contains the snapshot of 24 October 2026 used for the analysis and the video.

## 4. Story arc

| Step | Content in the app |
|---|---|
| **Hook** | Diesel ≈ €2.38/L, one tank ≈ €119, 23% of stations with a partial shortage |
| **Context** | Source, nature of the snapshot, cleaning rules, data-quality table |
| **Insight 1 – Map** | Every station coloured by its gap to the national median (blue/red diverging scale) |
| **Insight 2 – Rankings** | Top/bottom N departments: median + P10–P90 interval. Between- vs within-department comparison |
| **Insight 3 – Motorways** | Road vs motorway distribution: ≈ +10 cents/L on motorways |
| **Insight 4 – Shortages** | Share of stations with a shortage, by fuel and by region |
| **What-if** | Simulator: km/year, consumption, department, detour → net annual saving, detour break-even distance, E85 switch scenario |
| **Implications** | 3 key messages + next steps |

**Narrative patterns used:** comparing areas with a map, rankings & distributions, what-if exploration.

**Interactions:** fuel selection, region zoom (filters the whole app), number of departments shown, map
background, simulator sliders, expandable detail tables. Every chart has hover tooltips.

## 5. Cleaning and validation (`prepare_data.py`)

1. **Duplicates** on the station ID: none found.
2. **Coordinates:** the file stores them as degrees × 100,000 → divided; checked against a mainland-France bounding box.
3. **Stale prices:** a price not updated for **more than 30 days** before the extraction date is removed
   (e.g. 330 diesel prices). Assumption: such an old price no longer reflects reality.
4. **Implausible prices:** removed outside plausibility bounds (€1.50–3.50/L for diesel and petrol,
   €0.50–1.60 for E85, €0.50–1.80 for LPG). 6 prices removed.
5. **Shortages:** the "temporary shortage" column is split into one flag per fuel.
6. **Rankings:** departments with fewer than 10 stations for a given fuel are excluded (unstable medians).

All figures are written to `data/quality_report.json` and shown in the app (Context section).

## 6. Analysis methods

- Aggregations by department / region: median, P10, P90, min, max, counts.
- **Like-for-like comparison:** gap *between departments* = P90 − P10 of the department medians;
  gap *within a department* = median of the P10 − P90 spreads between stations. Medians and percentiles are
  used instead of means because they are robust to extreme values.
- Simulator: litres/year = km × consumption / 100; cost = litres × price (department P10, median or P90);
  detour cost = number of fill-ups × detour km × consumption / 100 × price; detour break-even distance =
  (median − P10) × 50 L / (consumption/100 × P10).

## 7. Limitations and assumptions

- **Snapshot:** no time dimension; conclusions hold for the extraction date.
- **Self-reported data:** possible errors, partly filtered out.
- **No station brand** in this feed: supermarkets cannot be compared with oil companies.
- **Deliberately simple simulator:** constant prices over the year, 50 L tank, one detour per fill-up.
  For E85, the extra consumption (+25% by default) and the kit cost (€1,000) are adjustable assumptions.
- **Shortages:** only temporary shortages are counted.
- Maps load their background from the internet (cdn.plot.ly / OpenStreetMap).

## 8. Possible improvements

- Add the daily archives (data.gouv.fr) for a before/after analysis over time.
- Combine with median income per municipality (INSEE, Filosofi) to measure the fuel burden on households.
- Find the cheapest station within a given radius of an address.

## 9. Colours

Colours come from a colour-blind-validated palette: blue `#2a78d6` / orange `#eb6834` for comparisons, and a
blue → grey → red diverging scale centred on the national median for the map.
