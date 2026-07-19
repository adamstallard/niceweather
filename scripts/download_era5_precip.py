#!/usr/bin/env python3
"""
download_era5_precip.py

Downloads hourly ERA5-Land total precipitation and aggregates it to a daily
total for each year. The raw hourly files are deleted after aggregation to
save disk space — only the daily summary NetCDF is kept.

Why hourly?
-----------
Precipitation is an accumulated variable and is intentionally excluded from
the ERA5-Land "daily statistics" dataset. We therefore download the hourly
data and aggregate it ourselves.

ERA5-Land accumulation notes
----------------------------
  - `total_precipitation` (tp) in ERA5-Land is accumulated from 00:00 UTC of
    each day. The value at 23:00 represents the entire day's accumulation.
  - Correct daily total = value at 23:00 × 1000  (to convert m → mm)
  - DO NOT use resample().sum() — this would re-sum already-cumulative values.

Requirements
------------
  pip install cdsapi xarray netCDF4 numpy

CDS Authentication
------------------
  ~/.cdsapirc must contain your API key. See download_era5_daily.py.

Usage
-----
  python download_era5_precip.py [--years 1995 2024] [--resume] [--keep-hourly]

Output
------
  data/raw/era5_precip/<year>/
    precip_daily.nc    daily total precipitation (mm)
"""

import argparse
import sys
import time
from pathlib import Path

import cdsapi
import numpy as np
import xarray as xr

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATASET = "reanalysis-era5-land"

MONTHS = [f"{m:02d}" for m in range(1, 13)]
DAYS = [f"{d:02d}" for d in range(1, 32)]
HOURS = [f"{h:02d}:00" for h in range(24)]

DEFAULT_START_YEAR = 1995
DEFAULT_END_YEAR = 2024

OUTPUT_ROOT = Path("data/raw/era5_precip")

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 60

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def file_is_valid_netcdf(path: Path) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        import netCDF4  # noqa: F401

        with netCDF4.Dataset(path):
            pass
        return True
    except Exception:
        return False


def download_hourly_precip(
    client: cdsapi.Client,
    year: int,
    out_path: Path,
) -> bool:
    """Download all hourly total_precipitation for a given year."""
    request = {
        "variable": "total_precipitation",
        "year": str(year),
        "month": MONTHS,
        "day": DAYS,
        "time": HOURS,
        "format": "netcdf",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(
                f"  [{attempt}/{MAX_RETRIES}] Downloading hourly precip"
                f" for {year} → {out_path.name}"
            )
            client.retrieve(DATASET, request, str(out_path))

            if not file_is_valid_netcdf(out_path):
                raise ValueError("Downloaded file failed NetCDF validation")

            size_mb = out_path.stat().st_size / 1_048_576
            print(f"  [OK] {out_path.name}  ({size_mb:.1f} MB)")
            return True

        except Exception as exc:
            print(f"  [ERROR] Attempt {attempt} failed: {exc}")
            if out_path.exists():
                out_path.unlink()
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_DELAY_SECONDS}s …")
                time.sleep(RETRY_DELAY_SECONDS)

    print(f"  [FAIL] All {MAX_RETRIES} attempts failed for precip {year}.")
    return False


def aggregate_to_daily(hourly_path: Path, daily_path: Path) -> bool:
    """
    Aggregate hourly ERA5-Land precipitation to a daily total (mm).

    ERA5-Land tp is accumulated from 00:00 UTC within each day. The last
    hour (23:00) therefore contains the full-day accumulation. We extract
    that value rather than summing, to avoid double-counting.

    Result is in millimetres (converted from metres).
    """
    print(f"  Aggregating {hourly_path.name} → {daily_path.name} …")
    try:
        ds = xr.open_dataset(hourly_path, engine="netcdf4")

        tp = ds["tp"]  # metres, accumulated since 00:00 UTC

        # Select the 23:00 time step of each day (last hourly value of the day)
        # which represents the full-day accumulation.
        daily_tp = (
            tp.resample(time="1D")
            .last()
            .rename("precip_mm")
            .assign_attrs(
                units="mm",
                long_name="Daily total precipitation",
                description=(
                    "Aggregated from ERA5-Land hourly total_precipitation. "
                    "Value is the 23:00 UTC accumulation × 1000 (m → mm)."
                ),
            )
        )

        # Convert m → mm
        daily_tp = (daily_tp * 1000.0).astype(np.float32)

        # Clamp negative values (small reanalysis artefacts near zero)
        daily_tp = daily_tp.clip(min=0.0)

        daily_tp.to_netcdf(daily_path)
        ds.close()

        size_mb = daily_path.stat().st_size / 1_048_576
        print(f"  [OK] Daily precip written ({size_mb:.1f} MB)")
        return True

    except Exception as exc:
        print(f"  [ERROR] Aggregation failed: {exc}")
        if daily_path.exists():
            daily_path.unlink()
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download ERA5-Land hourly precipitation and aggregate to daily."
    )
    parser.add_argument(
        "--years",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        default=[DEFAULT_START_YEAR, DEFAULT_END_YEAR],
        help=f"Year range inclusive. Default: {DEFAULT_START_YEAR} {DEFAULT_END_YEAR}",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Re-download even if daily file already exists.",
    )
    parser.add_argument(
        "--keep-hourly",
        action="store_true",
        help="Keep the raw hourly NetCDF after aggregation (large!).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_year, end_year = args.years
    resume = not args.no_resume
    keep_hourly = args.keep_hourly

    if start_year > end_year:
        print("ERROR: START year must be ≤ END year.", file=sys.stderr)
        sys.exit(1)

    years = list(range(start_year, end_year + 1))
    print("Nice Weather — ERA5-Land Precipitation Downloader")
    print(f"Years: {start_year}–{end_year}  ({len(years)} years)")
    print(f"Resume mode: {'ON' if resume else 'OFF'}")
    print(f"Keep hourly raw files: {'YES' if keep_hourly else 'NO (saves disk space)'}")
    print()

    client = cdsapi.Client()
    failures: list[int] = []

    for year in years:
        year_dir = OUTPUT_ROOT / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        print(f"── Year {year} ──────────────────────────────")

        daily_path = year_dir / "precip_daily.nc"
        hourly_path = year_dir / "precip_hourly_raw.nc"

        # Skip if daily file already valid and resume is on
        if resume and file_is_valid_netcdf(daily_path):
            print(f"  [SKIP] {daily_path.name} already exists and is valid.")
            print()
            continue

        # Step 1: Download hourly data
        ok = download_hourly_precip(client, year, hourly_path)
        if not ok:
            failures.append(year)
            print()
            continue

        # Step 2: Aggregate to daily
        ok = aggregate_to_daily(hourly_path, daily_path)
        if not ok:
            failures.append(year)
            print()
            continue

        # Step 3: Remove hourly file to reclaim disk space
        if not keep_hourly and hourly_path.exists():
            hourly_path.unlink()
            print(f"  [CLEAN] Removed {hourly_path.name}")

        print()

    # Summary
    n_fail = len(failures)
    n_ok = len(years) - n_fail
    print("=" * 50)
    print(f"Done.  {n_ok}/{len(years)} years succeeded.")
    if failures:
        print(f"\nFailed years ({n_fail}): {failures}")
        print("Re-run with the same command to retry failed years.")
        sys.exit(1)


if __name__ == "__main__":
    main()
