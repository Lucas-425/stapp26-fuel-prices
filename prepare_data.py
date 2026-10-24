"""
Data preparation — Fuel prices in France (real-time feed, v2)
Source: https://www.data.gouv.fr/fr/datasets/6407d088d4e23dc662022e2c

Usage:
    python prepare_data.py                      # uses data/raw/prix-des-carburants-en-france-flux-instantane-v2.csv
    python prepare_data.py path/to/file.csv     #   (downloaded from the official API if missing)

Outputs:
    data/stations_clean.csv   -> one row per station (wide format, useful columns only)
    data/prices_long.csv      -> one row per (station, fuel) with a valid price
    data/quality_report.json  -> cleaning figures, displayed in the app (transparency)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw" / "prix-des-carburants-en-france-flux-instantane-v2.csv"
OUT_DIR = ROOT / "data"
# Official CSV export of the same dataset (same columns as the file downloaded from data.gouv.fr)
EXPORT_URL = ("https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/"
              "prix-des-carburants-en-france-flux-instantane-v2/exports/csv?delimiter=%3B&use_labels=true")

# Fuel codes as they appear in the source file
FUELS = ["Gazole", "E10", "SP98", "SP95", "E85", "GPLc"]

# Plausibility bounds (€/L). Outside these bounds = probable data-entry error.
# Deliberately wide around the observed distribution; documented in the README.
PLAUSIBLE = {
    "Gazole": (1.50, 3.50),
    "E10": (1.50, 3.50),
    "SP98": (1.50, 3.50),
    "SP95": (1.50, 3.50),
    "E85": (0.50, 1.60),
    "GPLc": (0.50, 1.80),
}
# A price not updated for more than N days before the extraction date is considered stale.
STALE_DAYS = 30


def download_raw(path: Path = RAW) -> Path:
    """Download the latest snapshot from the official open-data API."""
    import urllib.request
    path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(EXPORT_URL, path)
    return path


def load_raw(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep=";", low_memory=False, dtype={"code_departement": str, "Code postal": str})


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    report: dict = {"n_raw": int(len(df))}

    # 1) Duplicate stations
    df = df.drop_duplicates(subset="id")
    report["n_after_dedup"] = int(len(df))

    # 2) Coordinates: stored as degrees x 100,000 (PTOLEMEE format)
    df["lat"] = df["latitude"] / 100_000
    df["lon"] = df["longitude"] / 100_000
    in_metro = df["lat"].between(41.0, 51.5) & df["lon"].between(-5.5, 10.0)
    report["n_bad_coords"] = int((~in_metro).sum())
    df.loc[~in_metro, ["lat", "lon"]] = np.nan

    # 3) Types / labels
    df["road_type"] = df["pop"].map({"A": "Motorway", "R": "Road"}).fillna("Unknown")
    df["open_24_7"] = df["Automate 24-24 (oui/non)"].eq("Oui")
    df["code_departement"] = df["code_departement"].astype(str).str.zfill(2)
    df["Ville"] = df["Ville"].astype(str).str.strip().str.title()
    services = df["Services proposés"].fillna("")
    df["n_services"] = services.apply(lambda s: 0 if s == "" else s.count(",") + 1)
    df["ev_charging"] = services.str.contains("Bornes électriques", regex=False)

    # 4) Update timestamps + extraction date (= most recent update in the file)
    for f in FUELS:
        df[f"updated_{f}"] = pd.to_datetime(df[f"Prix {f} mis à jour le"], utc=True, errors="coerce")
    snapshot = max(df[f"updated_{f}"].max() for f in FUELS)
    report["snapshot_utc"] = snapshot.isoformat()

    # 5) Prices: plausibility + freshness
    report["prices"] = {}
    for f in FUELS:
        p = df[f"Prix {f}"]
        lo, hi = PLAUSIBLE[f]
        implausible = p.notna() & ~p.between(lo, hi)
        stale = p.notna() & (snapshot - df[f"updated_{f}"] > pd.Timedelta(days=STALE_DAYS))
        report["prices"][f] = {
            "raw_non_null": int(p.notna().sum()),
            "implausible_removed": int(implausible.sum()),
            "stale_removed": int((stale & ~implausible).sum()),
        }
        df[f"price_{f}"] = p.where(~implausible & ~stale)
        report["prices"][f]["kept"] = int(df[f"price_{f}"].notna().sum())

    # 6) Temporary shortages ("ruptures")
    rt = df["Carburants en rupture temporaire"].fillna("")
    df["shortage_any"] = rt.ne("")
    for f in FUELS:
        df[f"shortage_{f}"] = rt.str.split(r"[;,]").apply(lambda lst, f=f: f in lst)
    report["pct_stations_shortage"] = round(float(df["shortage_any"].mean()) * 100, 1)

    keep = (
        ["id", "Adresse", "Ville", "Code postal", "Département", "code_departement", "Région",
         "lat", "lon", "road_type", "open_24_7", "n_services", "ev_charging", "shortage_any"]
        + [f"price_{f}" for f in FUELS]
        + [f"shortage_{f}" for f in FUELS]
    )
    wide = df[keep].rename(columns={"Adresse": "address", "Ville": "city", "Code postal": "postcode",
                                    "Département": "department", "code_departement": "department_code",
                                    "Région": "region"})

    long = wide.melt(
        id_vars=["id", "city", "department", "department_code", "region", "lat", "lon", "road_type", "open_24_7"],
        value_vars=[f"price_{f}" for f in FUELS], var_name="fuel", value_name="price",
    ).dropna(subset=["price"])
    long["fuel"] = long["fuel"].str.replace("price_", "", regex=False)

    report["n_stations_final"] = int(len(wide))
    report["n_prices_final"] = int(len(long))
    return wide, long, report


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else RAW
    if not path.exists() and path == RAW:
        print("Raw file not found: downloading the latest snapshot from data.economie.gouv.fr…")
        download_raw(path)
    if not path.exists():
        sys.exit(f"File not found: {path}\nDownload the CSV from data.gouv.fr (see README).")
    wide, long, report = clean(load_raw(path))
    OUT_DIR.mkdir(exist_ok=True)
    wide.to_csv(OUT_DIR / "stations_clean.csv", index=False)
    long.to_csv(OUT_DIR / "prices_long.csv", index=False)
    (OUT_DIR / "quality_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
