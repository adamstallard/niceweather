#!/usr/bin/env python3
"""
process_climate.py

Processes downloaded ERA5-Land data to produce a compact binary file
(data/processed/perfect_weather.bin) containing per-cell daily probability
scores for "perfect weather" across all 365 calendar days of the year.

Algorithm
---------
For each 0.1° ERA5 grid cell:
  For each calendar day (1–365):
    1. Apply a ±7-day moving window (15 days × 30 years = 450 observations)
    2. Count observations meeting ALL three "perfect day" criteria:
         a. max temperature ≥ 75°F (≥ 23.89°C = 297.04 K)
         b. max dew point < 60°F (< 15.56°C = 288.71 K)
         c. total cloud cover < 50% (fraction 0.5, mostly sunny)
    3. probability = count / observations
    4. Discard cells where probability < 0.50 for ALL days

Population masking:
    Cells with fewer than MIN_POPULATION people (scaled from WorldPop)
    are excluded entirely.

Output format: perfect_weather.bin
-----------------------------------
  Header (20 bytes):
    uint32: n_cells  — number of populated cells with ≥1 day ≥50% prob
    uint16: n_days   — always 365
    uint16: n_lat    — number of latitude indices in ERA5 grid
    uint16: n_lon    — number of longitude indices in ERA5 grid
    float32: lat_min, lat_max, lon_min, lon_max — grid bounds

  Per cell (4 + 365 bytes):
    uint16: lat_idx  — index into ERA5 latitude axis
    uint16: lon_idx  — index into ERA5 longitude axis
    uint8[365]: prob — probability 0..100 (0=<50%, 50=50%, 100=100%)

Usage
-----
  python scripts/process_climate.py [--years 1995 2024]
  python scripts/process_climate.py --calibrate-only [--solar-threshold 15]

Requirements
------------
  pip install xarray netCDF4 numpy scipy rasterio tqdm
"""

import argparse
import struct
import sys
from pathlib import Path

import numpy as np
import rasterio
import rasterio.transform
import xarray as xr
from rasterio.warp import reproject, Resampling
from tqdm import tqdm

# ---------------------------------------------------------------------------
# Configuration — thresholds
# ---------------------------------------------------------------------------

# Temperature: max 2m temp must reach ≥ 75°F
TMAX_THRESHOLD_K = 273.15 + 23.889  # 75°F in Kelvin = 297.04 K

# Dew point: max 2m dew point must be < 60°F (not uncomfortably humid)
DEWPOINT_THRESHOLD_K = 273.15 + 15.556  # 60°F in Kelvin = 288.71 K

# Cloud cover: must be < 50% (mostly sunny)
# Fraction 0–1, where 0 = clear, 1 = completely overcast
CLOUD_COVER_THRESHOLD = 0.5

# Population mask: minimum people per ERA5 cell (~0.1° × 0.1°)
# WorldPop is per km² at 1km resolution. ERA5 cells at 0.1° are ~11km²,
# so a population of 100 in an ERA5 cell = very sparse habitation.
MIN_POPULATION = 100

# Window: ±N days around each calendar day
WINDOW_DAYS = 7  # → 15-day window × 30 years = 450 obs

# Probability cutoff: only show cells above this threshold
PROB_CUTOFF = 0.50

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DATA_ROOT = Path("data")
ERA5_DAILY = DATA_ROOT / "raw/era5_daily"
WORLDPOP_PATH = DATA_ROOT / "raw/worldpop/ppp_2020_1km_Aggregated.tif"
OUTPUT_DIR = DATA_ROOT / "processed"
OUTPUT_FILE = OUTPUT_DIR / "perfect_weather.bin"

# ---------------------------------------------------------------------------
# Reference calibration sites (for threshold validation)
# ---------------------------------------------------------------------------

CALIBRATION_SITES = {
    "Phoenix, AZ (hot sunny summer)": (33.4, -112.1),
    "Seattle, WA (cloudy winter)": (47.6, -122.3),
    "Honolulu, HI (year-round pleasant)": (21.3, -157.8),
    "London, UK (famously grey)": (51.5, -0.1),
    "Sahara Desert, Algeria (extreme hot)": (23.0, 3.0),
    "Medellin, Colombia (spring city)": (6.2, -75.6),
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def load_era5_variable(var_name: str, years: list[int]) -> xr.DataArray:
    """Load ERA5 daily statistics variable across all years."""
    arrays = []
    for year in tqdm(years, desc=f"Loading {var_name}", unit="yr"):
        path = ERA5_DAILY / str(year) / "data.nc"

        if not path.exists():
            print(f"  [WARN] Missing: {path}", file=sys.stderr)
            continue

        ds = xr.open_dataset(path, engine="netcdf4")

        # Map our names to ERA5 variable names
        varkey = {
            "tmax": "t2m",
            "dewpoint": "d2m",
            "cloudcover": "tcc",
        }.get(var_name, var_name)

        if varkey not in ds:
            # Try first data variable if exact name not found
            varkey = list(ds.data_vars)[0]

        arrays.append(ds[varkey])

    if not arrays:
        raise FileNotFoundError(
            f"No data found for '{var_name}'. "
            "Run: python scripts/download_era5_daily.py"
        )

    return xr.concat(arrays, dim="time")


def build_population_mask(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """
    Resample WorldPop 2020 (1km) onto the ERA5 grid (0.1°).
    Returns a boolean mask: True = keep (population ≥ MIN_POPULATION).
    """
    if not WORLDPOP_PATH.exists():
        print(
            "[WARN] WorldPop file not found. Using all-land mask instead. "
            "Run scripts/download_worldpop.py for accurate population masking.",
            file=sys.stderr,
        )
        return np.ones((len(lat), len(lon)), dtype=bool)

    print("  Resampling WorldPop to ERA5 grid …")
    n_lat, n_lon = len(lat), len(lon)
    pop_on_era5 = np.zeros((n_lat, n_lon), dtype=np.float32)

    # ERA5 grid transform (note: lat may be descending)
    dlat = float(lat[1] - lat[0])
    dlon = float(lon[1] - lon[0])
    era5_transform = rasterio.transform.from_bounds(
        west=float(lon[0]) - abs(dlon) / 2,
        south=float(lat[-1]) - abs(dlat) / 2,
        east=float(lon[-1]) + abs(dlon) / 2,
        north=float(lat[0]) + abs(dlat) / 2,
        width=n_lon,
        height=n_lat,
    )

    with rasterio.open(WORLDPOP_PATH) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=pop_on_era5,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=era5_transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.sum,  # sum population within each ERA5 cell
        )

    pop_on_era5 = np.nan_to_num(pop_on_era5, nan=0.0).clip(min=0)
    mask = pop_on_era5 >= MIN_POPULATION
    n_populated = mask.sum()
    print(f"  Populated ERA5 cells (≥{MIN_POPULATION} people): {n_populated:,}")
    return mask


def compute_calendar_day_index(time: np.ndarray) -> np.ndarray:
    """Return day-of-year (1–365) for each timestamp, clamping Feb-29 to day 59."""
    import pandas as pd

    doys = pd.DatetimeIndex(time).day_of_year.values.astype(np.int16)
    # Clamp leap-year day 366 to 365 (Dec 31 treatment) and day 60 (Feb 29) to 59
    doys = np.where(doys == 366, 365, doys)
    doys = np.where(doys == 60, 59, doys)  # Feb 29 → Feb 28 slot
    return doys


def calibration_report(
    tmax: xr.DataArray,
    dewpoint: xr.DataArray,
    cloudcover: xr.DataArray,
) -> None:
    """Print stats for calibration sites to validate thresholds."""
    print("\n── Calibration report ──────────────────────────────────")
    print(f"{'Site':<40} {'Tmax≥75F':>8} {'DP<60F':>8} {'Cloud<50%':>10}")
    print("─" * 70)

    lat_vals = tmax.latitude.values if "latitude" in tmax.coords else tmax.lat.values
    lon_vals = tmax.longitude.values if "longitude" in tmax.coords else tmax.lon.values

    for name, (site_lat, site_lon) in CALIBRATION_SITES.items():
        ilat = int(np.argmin(np.abs(lat_vals - site_lat)))
        ilon = int(np.argmin(np.abs(lon_vals - site_lon)))

        t = tmax.isel(latitude=ilat, longitude=ilon).values
        d = dewpoint.isel(latitude=ilat, longitude=ilon).values
        c = cloudcover.isel(latitude=ilat, longitude=ilon).values

        n = len(t)
        pct_tmax = 100 * np.sum(t >= TMAX_THRESHOLD_K) / n
        pct_dp = 100 * np.sum(d < DEWPOINT_THRESHOLD_K) / n
        pct_cloud = 100 * np.sum(c < CLOUD_COVER_THRESHOLD) / n

        print(f"{name:<40} {pct_tmax:7.1f}% {pct_dp:7.1f}% {pct_cloud:9.1f}%")
    print("─" * 70)
    print()


# ---------------------------------------------------------------------------
# Main processing loop
# ---------------------------------------------------------------------------


def compute_probability_map(
    tmax: np.ndarray,   # shape (T, lat, lon) — Kelvin
    dewpoint: np.ndarray,  # shape (T, lat, lon) — Kelvin
    cloudcover: np.ndarray,  # shape (T, lat, lon) — fraction 0–1
    doys: np.ndarray,   # shape (T,) day-of-year 1..365
    pop_mask: np.ndarray,  # shape (lat, lon) bool
) -> np.ndarray:
    """
    Compute per-cell daily probabilities.
    Returns array shape (lat, lon, 365), dtype float32, values 0.0–1.0.
    """
    T, n_lat, n_lon = tmax.shape
    prob = np.zeros((n_lat, n_lon, 365), dtype=np.float32)

    # Pre-compute per-day "perfect" boolean array
    perfect = (
        (tmax >= TMAX_THRESHOLD_K) &
        (dewpoint < DEWPOINT_THRESHOLD_K) &
        (cloudcover < CLOUD_COVER_THRESHOLD)
    )  # shape (T, lat, lon)

    print("  Computing per-cell probabilities …")
    for cal_day in tqdm(range(1, 366), desc="Calendar days", unit="day"):
        # Build index of all observations within ±WINDOW_DAYS of this cal day
        lo = cal_day - WINDOW_DAYS
        hi = cal_day + WINDOW_DAYS

        if lo < 1 and hi > 365:
            idx = np.ones(T, dtype=bool)
        elif lo < 1:
            idx = (doys <= hi) | (doys >= (365 + lo))
        elif hi > 365:
            idx = (doys >= lo) | (doys <= (hi - 365))
        else:
            idx = (doys >= lo) & (doys <= hi)

        n_obs = idx.sum()
        if n_obs == 0:
            continue

        # Sum over matching time steps
        window_perfect = perfect[idx]  # shape (n_obs, lat, lon)
        prob[:, :, cal_day - 1] = window_perfect.sum(axis=0) / n_obs

    # Zero out unpopulated cells
    prob[~pop_mask] = 0.0
    return prob


# ---------------------------------------------------------------------------
# Binary serialization
# ---------------------------------------------------------------------------


def write_output(prob: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> None:
    """
    Write compact binary output.
    Only writes cells where at least one day has probability ≥ PROB_CUTOFF.
    Probabilities are stored as uint8 (0–100).
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    n_lat, n_lon, n_days = prob.shape
    assert n_days == 365

    # Find cells with ≥1 day above cutoff
    max_prob = prob.max(axis=2)
    active = max_prob >= PROB_CUTOFF
    lat_idxs, lon_idxs = np.where(active)
    n_cells = len(lat_idxs)

    print(f"\n  Active cells (≥{PROB_CUTOFF:.0%} on at least 1 day): {n_cells:,}")

    # Quantize to uint8 (0–100), clamping below cutoff to 0
    prob_u8 = (prob * 100).clip(0, 100).astype(np.uint8)
    prob_u8[prob < PROB_CUTOFF] = 0

    with open(OUTPUT_FILE, "wb") as f:
        # Header (20 bytes)
        f.write(struct.pack(">I", n_cells))        # 4 bytes: number of cells
        f.write(struct.pack(">H", n_days))         # 2 bytes: days (365)
        f.write(struct.pack(">H", n_lat))          # 2 bytes: lat grid size
        f.write(struct.pack(">H", n_lon))          # 2 bytes: lon grid size
        # Lat/lon bounds (4 × float32 = 16 bytes)
        f.write(struct.pack(">f", float(lat[0])))   # lat_min
        f.write(struct.pack(">f", float(lat[-1])))  # lat_max
        f.write(struct.pack(">f", float(lon[0])))   # lon_min
        f.write(struct.pack(">f", float(lon[-1])))  # lon_max

        # Per-cell data
        for i_lat, i_lon in zip(lat_idxs, lon_idxs):
            f.write(struct.pack(">H", int(i_lat)))   # 2 bytes: lat index
            f.write(struct.pack(">H", int(i_lon)))   # 2 bytes: lon index
            f.write(prob_u8[i_lat, i_lon].tobytes()) # 365 bytes: probabilities

    size_mb = OUTPUT_FILE.stat().st_size / 1_048_576
    print(f"  Output written: {OUTPUT_FILE}  ({size_mb:.1f} MB)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute perfect-weather probability maps from ERA5 data."
    )
    parser.add_argument(
        "--years",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        default=[1995, 2024],
    )
    parser.add_argument(
        "--calibrate-only",
        action="store_true",
        help="Only print calibration report; do not write output file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_year, end_year = args.years
    years = list(range(start_year, end_year + 1))

    print("Nice Weather — Climate Processing Pipeline")
    print(f"Years: {start_year}–{end_year}  ({len(years)} years)")
    print(f"Window: ±{WINDOW_DAYS} days → {2 * WINDOW_DAYS + 1} days × {len(years)} years")
    print(f"  = {(2 * WINDOW_DAYS + 1) * len(years)} max observations per calendar day")
    print(f"\nThresholds:")
    print(f"  Temperature   ≥ {TMAX_THRESHOLD_K - 273.15:.1f}°C (75°F)")
    print(f"  Dew point     < {DEWPOINT_THRESHOLD_K - 273.15:.1f}°C (60°F)")
    print(f"  Cloud cover   < {CLOUD_COVER_THRESHOLD * 100:.0f}% (mostly sunny)")
    print()

    # Load all variables
    print("── Loading ERA5 data ──────────────────────────────────")
    tmax_da = load_era5_variable("tmax", years)
    dewpoint_da = load_era5_variable("dewpoint", years)
    cloudcover_da = load_era5_variable("cloudcover", years)

    # Calibration report
    calibration_report(tmax_da, dewpoint_da, cloudcover_da)

    if args.calibrate_only:
        print("Calibration-only mode — exiting without writing output.")
        return

    # Extract lat/lon coordinates
    lat_key = "latitude" if "latitude" in tmax_da.coords else "lat"
    lon_key = "longitude" if "longitude" in tmax_da.coords else "lon"
    lat = tmax_da[lat_key].values
    lon = tmax_da[lon_key].values

    # Build population mask
    print("\n── Building population mask ───────────────────────────")
    pop_mask = build_population_mask(lat, lon)

    # Load data into memory as numpy arrays
    print("\n── Loading data into memory ───────────────────────────")
    tmax_np = tmax_da.values.astype(np.float32)
    dewpoint_np = dewpoint_da.values.astype(np.float32)
    cloudcover_np = cloudcover_da.values.astype(np.float32)
    doys = compute_calendar_day_index(tmax_da.time.values)

    # Compute probability maps
    print("\n── Computing probability maps ─────────────────────────")
    prob = compute_probability_map(
        tmax_np, dewpoint_np, cloudcover_np, doys, pop_mask
    )

    # Write output
    print("\n── Writing output ─────────────────────────────────────")
    write_output(prob, lat, lon)

    print("\nDone! ✓")
    print(f"Next: open web/index.html in a browser to preview the map.")


if __name__ == "__main__":
    main()
