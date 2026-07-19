#!/usr/bin/env python3
"""
download_era5_daily.py

Downloads ERA5-Land post-processed daily statistics from the Copernicus
Climate Data Store (CDS) for the variables needed to assess "perfect weather":

  - daily maximum 2m temperature        (for the ≥75°F check)
  - daily maximum 2m dew point          (for the humidity check)
  - daily mean surface solar radiation  (for the "mostly sunny" check)

Precipitation is intentionally NOT included here — it is an accumulated
variable excluded from the daily-statistics dataset. See download_era5_precip.py.

Requirements
------------
  pip install cdsapi>=0.7.7

CDS Authentication
------------------
  You need a free Copernicus account and an API key placed in:
    ~/.cdsapirc
  Format:
    url: https://cds.climate.copernicus.eu/api
    key: <your-api-key>

  Get your key at: https://cds.climate.copernicus.eu/user/login

Usage
-----
  python download_era5_daily.py [--years 1995 2024] [--resume]

Output
------
  data/raw/era5_daily/<year>/
    tmax.nc       daily max 2m temperature (K)
    dewpoint.nc   daily max 2m dew point (K)
    solar.nc      daily mean surface solar radiation downwards (J/m²)
"""

import argparse
import hashlib
import sys
import time
from pathlib import Path

import cdsapi

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATASET = "derived-era5-land-daily-statistics"

# Variables to download from the daily statistics dataset
VARIABLES = [
    {
        "name": "tmax",
        "variable": "2m_temperature",
        "daily_statistic": "daily_maximum",
        "description": "daily max 2m temperature",
    },
    {
        "name": "dewpoint",
        "variable": "2m_dewpoint_temperature",
        "daily_statistic": "daily_maximum",
        "description": "daily max 2m dew point temperature",
    },
    {
        "name": "solar",
        "variable": "surface_solar_radiation_downwards",
        "daily_statistic": "daily_mean",
        "description": "daily mean surface solar radiation downwards",
    },
]

MONTHS = [f"{m:02d}" for m in range(1, 13)]
DAYS = [f"{d:02d}" for d in range(1, 32)]

# CDS requests are year-by-year to keep request sizes manageable and allow
# easy resumption if interrupted.
DEFAULT_START_YEAR = 1995
DEFAULT_END_YEAR = 2024

OUTPUT_ROOT = Path("data/raw/era5_daily")

# How many times to retry a failed download before giving up
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 60

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def md5(path: Path) -> str:
    """Compute MD5 hash of a file for basic integrity checks."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def file_is_valid_netcdf(path: Path) -> bool:
    """Return True if the file exists, is non-empty, and opens as a NetCDF."""
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        import netCDF4  # noqa: F401

        with netCDF4.Dataset(path):
            pass
        return True
    except Exception:
        return False


def download_variable(
    client: cdsapi.Client,
    year: int,
    var: dict,
    out_path: Path,
    *,
    resume: bool = True,
) -> bool:
    """
    Download one variable for one year.
    Returns True on success, False on failure.
    """
    if resume and file_is_valid_netcdf(out_path):
        print(f"  [SKIP] {out_path.name} already exists and is valid.")
        return True

    request = {
        "variable": var["variable"],
        "year": str(year),
        "month": MONTHS,
        "day": DAYS,
        "daily_statistic": var["daily_statistic"],
        # Use UTC+00:00 for consistency. The probability model uses a ±7-day
        # calendar-day window so local-time offsets matter little at this step.
        "time_zone": "utc+00:00",
        "frequency": "1_hourly",
        "format": "netcdf",
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(
                f"  [{attempt}/{MAX_RETRIES}] Downloading {var['description']}"
                f" for {year} → {out_path.name}"
            )
            client.retrieve(DATASET, request, str(out_path))

            if not file_is_valid_netcdf(out_path):
                raise ValueError(f"Downloaded file failed validation: {out_path}")

            size_mb = out_path.stat().st_size / 1_048_576
            print(f"  [OK] {out_path.name}  ({size_mb:.1f} MB)")
            return True

        except Exception as exc:
            print(f"  [ERROR] Attempt {attempt} failed: {exc}")
            # Remove the potentially corrupt partial file
            if out_path.exists():
                out_path.unlink()
            if attempt < MAX_RETRIES:
                print(f"  Retrying in {RETRY_DELAY_SECONDS}s …")
                time.sleep(RETRY_DELAY_SECONDS)

    print(f"  [FAIL] All {MAX_RETRIES} attempts failed for {var['name']} {year}.")
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download ERA5-Land daily statistics (temp, dew point, solar) "
        "for the Nice Weather project."
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
        help="Re-download files even if they already exist.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_year, end_year = args.years
    resume = not args.no_resume

    if start_year > end_year:
        print("ERROR: START year must be ≤ END year.", file=sys.stderr)
        sys.exit(1)

    years = list(range(start_year, end_year + 1))
    print(f"Nice Weather — ERA5-Land Daily Statistics Downloader")
    print(f"Years: {start_year}–{end_year}  ({len(years)} years)")
    print(f"Variables: {', '.join(v['name'] for v in VARIABLES)}")
    print(f"Resume mode: {'ON' if resume else 'OFF'}")
    print()

    client = cdsapi.Client()

    failures: list[tuple[int, str]] = []

    for year in years:
        year_dir = OUTPUT_ROOT / str(year)
        year_dir.mkdir(parents=True, exist_ok=True)
        print(f"── Year {year} ──────────────────────────────")

        for var in VARIABLES:
            out_path = year_dir / f"{var['name']}.nc"
            success = download_variable(client, year, var, out_path, resume=resume)
            if not success:
                failures.append((year, var["name"]))

        print()

    # Summary
    total = len(years) * len(VARIABLES)
    n_fail = len(failures)
    print("=" * 50)
    print(f"Done.  {total - n_fail}/{total} files succeeded.")
    if failures:
        print(f"\nFailed downloads ({n_fail}):")
        for year, name in failures:
            print(f"  {year}/{name}.nc")
        print("\nRe-run with the same command to retry failed files.")
        sys.exit(1)


if __name__ == "__main__":
    main()
