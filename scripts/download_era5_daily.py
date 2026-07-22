#!/usr/bin/env python3
"""
download_era5_daily.py

Downloads ERA5 post-processed daily statistics from Copernicus CDS for
perfect weather analysis:

  - 2m temperature (daily maximum) — for ≥75°F check
  - 2m dew point (daily maximum) — for humidity check (< 72°F)
  - Total cloud cover (daily maximum) — for "sunny" check (current default)

Uses the exact Copernicus API request syntax (year-by-year for resumability).

Requirements
  pip install cdsapi

CDS Authentication
  You need ~/.cdsapirc with your API key:
    url: https://cds.climate.copernicus.eu/api
    key: <your-api-key>

Usage
  python scripts/download_era5_daily.py --years 1995 2024
  python scripts/download_era5_daily.py --years 2015 2024  # Test run

  # After all years are downloaded, upgrade cloud cover to daily mean:
  python scripts/download_era5_daily.py --years 1995 2024 --cloud-mean
  # This downloads ONLY total_cloud_cover (daily_mean) for each month and
  # merges it into the existing data.nc, replacing the daily-max tcc variable.
  # The existing tmax and dew point data are preserved untouched.

Output
  data/raw/era5_daily/<year>/data.nc                  — Combined annual data
  data/raw/era5_daily/<year>/monthly/*.nc             — Monthly files (max vars)
  data/raw/era5_daily/<year>/monthly_cloud_mean/*.nc  — Monthly cloud-mean files
"""

import argparse
import sys
import time
import zipfile
from pathlib import Path

import cdsapi

# Configuration
DATASET = "derived-era5-single-levels-daily-statistics"
OUTPUT_ROOT = Path("data/raw/era5_daily")
MONTHS = [f"{m:02d}" for m in range(1, 13)]
DAYS = [f"{d:02d}" for d in range(1, 32)]
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 30


def is_valid_netcdf(path: Path) -> bool:
    """Check if file exists and is valid NetCDF."""
    if not path.exists():
        return False
    try:
        import netCDF4
        netCDF4.Dataset(path, "r").close()
        return True
    except Exception:
        return False


def download_year(client: cdsapi.Client, year: int, output_path: Path) -> bool:
    """Download ERA5 daily for one year, month-by-month to avoid API size limits."""
    if output_path.exists() and is_valid_netcdf(output_path):
        size_mb = output_path.stat().st_size / 1_048_576
        print(f"  [SKIP] {output_path.name} ({size_mb:.1f} MB)")
        return True

    # Create temp files for each month, then combine
    temp_dir = output_path.parent / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    month_files = []

    for month_int in range(1, 13):
        month_str = f"{month_int:02d}"
        month_file = temp_dir / f"{year}_{month_str}.nc"
        month_files.append(month_file)

        if month_file.exists() and is_valid_netcdf(month_file):
            size_mb = month_file.stat().st_size / 1_048_576
            print(f"    [SKIP] {year}-{month_str} ({size_mb:.1f} MB)")
            continue

        request = {
            "product_type": "reanalysis",
            "variable": [
                "2m_dewpoint_temperature",
                "2m_temperature",
                "total_cloud_cover"
            ],
            "year": str(year),
            "month": month_str,
            "day": DAYS,
            "daily_statistic": "daily_maximum",
            "time_zone": "utc+00:00",
            "frequency": "6_hourly",
            "format": "netcdf"
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"    [{attempt}/{MAX_RETRIES}] Downloading {year}-{month_str}")
                # Download to a temp zip file
                temp_zip = month_file.with_suffix('.zip')
                client.retrieve(DATASET, request, str(temp_zip))

                # Extract NetCDF file(s) from ZIP. CDS may deliver one .nc per
                # variable — merge them into a single monthly file.
                with zipfile.ZipFile(temp_zip, 'r') as zf:
                    nc_files = [f for f in zf.namelist() if f.endswith('.nc')]
                    if not nc_files:
                        raise ValueError("No .nc file found in downloaded ZIP")
                    for nc_name in nc_files:
                        zf.extract(nc_name, temp_dir)

                if len(nc_files) == 1:
                    (temp_dir / nc_files[0]).rename(month_file)
                else:
                    import xarray as xr
                    parts = [xr.open_dataset(temp_dir / n) for n in nc_files]
                    merged = xr.merge(parts, compat="override")
                    merged.to_netcdf(str(month_file))
                    for p in parts:
                        p.close()
                    for n in nc_files:
                        (temp_dir / n).unlink()

                # Clean up zip
                temp_zip.unlink()

                if not is_valid_netcdf(month_file):
                    raise ValueError("NetCDF validation failed")

                size_mb = month_file.stat().st_size / 1_048_576
                print(f"    [OK] {year}-{month_str} ({size_mb:.1f} MB)")
                break

            except Exception as exc:
                print(f"    [ERROR] Attempt {attempt}: {exc}", file=sys.stderr)
                if month_file.exists():
                    month_file.unlink()
                temp_zip = month_file.with_suffix('.zip')
                if temp_zip.exists():
                    temp_zip.unlink()
                if attempt < MAX_RETRIES:
                    print(f"    Retrying in {RETRY_DELAY_SECONDS}s …")
                    time.sleep(RETRY_DELAY_SECONDS)
        else:
            print(f"    [FAIL] {MAX_RETRIES} attempts failed for {year}-{month_str}", file=sys.stderr)
            return False

    # Combine all monthly files into one
    print(f"  Combining months for {year} → {output_path.name}")
    try:
        import xarray as xr
        datasets = [xr.open_dataset(f) for f in month_files]
        # CDS daily statistics use 'valid_time' as the time dimension
        time_dim = "valid_time" if "valid_time" in datasets[0].dims else "time"
        combined = xr.concat(datasets, dim=time_dim)
        combined.to_netcdf(str(output_path))
        for ds in datasets:
            ds.close()

        # Keep monthly files in a subdirectory for reproducibility and debugging
        monthly_dir = output_path.parent / "monthly"
        monthly_dir.mkdir(parents=True, exist_ok=True)
        for f in month_files:
            f.rename(monthly_dir / f.name)

        size_mb = output_path.stat().st_size / 1_048_576
        print(f"  [OK] Combined {year} ({size_mb:.1f} MB)")
        try:
            rel = monthly_dir.resolve().relative_to(Path.cwd().resolve())
        except ValueError:
            rel = monthly_dir
        print(f"  [OK] Monthly files archived to {rel}")
        return True
    except Exception as exc:
        print(f"  [ERROR] Failed to combine months: {exc}", file=sys.stderr)
        return False


def download_cloud_mean_year(client: cdsapi.Client, year: int, output_path: Path) -> bool:
    """Download ONLY total_cloud_cover (daily_mean) and merge into existing data.nc.

    The existing data.nc must already contain tmax and dew point from the
    normal download_year() run. This function:
      1. Downloads tcc daily_mean month-by-month into monthly_cloud_mean/
      2. Combines them into a single annual tcc_mean DataArray
      3. Replaces the 'tcc' variable in data.nc with the mean values
         (the existing tmax/dew point data are not touched)

    Existing monthly_cloud_mean/*.nc files are skipped (resume-safe).
    The original monthly/*.nc files are never touched.
    """
    import xarray as xr

    if not output_path.exists() or not is_valid_netcdf(output_path):
        print(f"  [ERROR] {output_path} does not exist — run normal download first",
              file=sys.stderr)
        return False

    cloud_mean_dir = output_path.parent / "monthly_cloud_mean"
    cloud_mean_dir.mkdir(parents=True, exist_ok=True)
    month_files = []

    for month_int in range(1, 13):
        month_str = f"{month_int:02d}"
        month_file = cloud_mean_dir / f"{year}_{month_str}_cloud_mean.nc"
        month_files.append(month_file)

        if month_file.exists() and is_valid_netcdf(month_file):
            size_mb = month_file.stat().st_size / 1_048_576
            print(f"    [SKIP] {year}-{month_str} cloud mean ({size_mb:.1f} MB)")
            continue

        request = {
            "product_type": "reanalysis",
            "variable": ["total_cloud_cover"],
            "year": str(year),
            "month": month_str,
            "day": DAYS,
            "daily_statistic": "daily_mean",
            "time_zone": "utc+00:00",
            "frequency": "1_hourly",
            "format": "netcdf"
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"    [{attempt}/{MAX_RETRIES}] Downloading {year}-{month_str} cloud mean")
                temp_zip = month_file.with_suffix('.zip')
                client.retrieve(DATASET, request, str(temp_zip))

                with zipfile.ZipFile(temp_zip, 'r') as zf:
                    nc_files = [f for f in zf.namelist() if f.endswith('.nc')]
                    if not nc_files:
                        raise ValueError("No .nc file found in downloaded ZIP")
                    for nc_name in nc_files:
                        zf.extract(nc_name, cloud_mean_dir)

                if len(nc_files) == 1:
                    (cloud_mean_dir / nc_files[0]).rename(month_file)
                else:
                    parts = [xr.open_dataset(cloud_mean_dir / n) for n in nc_files]
                    merged = xr.merge(parts, compat="override")
                    merged.to_netcdf(str(month_file))
                    for p in parts:
                        p.close()
                    for n in nc_files:
                        (cloud_mean_dir / n).unlink()

                temp_zip.unlink()

                if not is_valid_netcdf(month_file):
                    raise ValueError("NetCDF validation failed")

                size_mb = month_file.stat().st_size / 1_048_576
                print(f"    [OK] {year}-{month_str} cloud mean ({size_mb:.1f} MB)")
                break

            except Exception as exc:
                print(f"    [ERROR] Attempt {attempt}: {exc}", file=sys.stderr)
                if month_file.exists():
                    month_file.unlink()
                temp_zip = month_file.with_suffix('.zip')
                if temp_zip.exists():
                    temp_zip.unlink()
                if attempt < MAX_RETRIES:
                    print(f"    Retrying in {RETRY_DELAY_SECONDS}s …")
                    time.sleep(RETRY_DELAY_SECONDS)
        else:
            print(f"    [FAIL] {MAX_RETRIES} attempts failed for {year}-{month_str} cloud mean",
                  file=sys.stderr)
            return False

    # Combine monthly cloud-mean files and merge into existing data.nc
    print(f"  Merging cloud mean into {output_path.name} for {year}")
    try:
        datasets = [xr.open_dataset(f) for f in month_files]
        time_dim = "valid_time" if "valid_time" in datasets[0].dims else "time"
        cloud_annual = xr.concat(datasets, dim=time_dim)
        for ds in datasets:
            ds.close()

        # Load existing data.nc, drop old tcc, add new mean tcc
        existing = xr.open_dataset(str(output_path))
        updated = xr.merge(
            [existing.drop_vars("tcc", errors="ignore"), cloud_annual[["tcc"]]],
            compat="override"
        )
        existing.close()

        # Write to a temp file first, then atomically replace
        tmp_out = output_path.with_suffix(".tmp.nc")
        updated.to_netcdf(str(tmp_out))
        tmp_out.replace(output_path)

        size_mb = output_path.stat().st_size / 1_048_576
        print(f"  [OK] {year} data.nc updated with mean cloud cover ({size_mb:.1f} MB)")
        return True
    except Exception as exc:
        print(f"  [ERROR] Failed to merge cloud mean for {year}: {exc}", file=sys.stderr)
        return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download ERA5 daily statistics for perfect weather analysis."
    )
    parser.add_argument(
        "--years",
        nargs=2,
        type=int,
        metavar=("START", "END"),
        default=[1995, 2024],
    )
    parser.add_argument(
        "--cloud-mean",
        action="store_true",
        help=(
            "Download ONLY total_cloud_cover (daily_mean) and merge it into "
            "existing data.nc files. Existing tmax/dew point data and monthly "
            "files are never deleted. Run this after all years are downloaded "
            "to upgrade from max to mean cloud cover (threshold: 50%% vs 56%%)."
        ),
    )
    args = parser.parse_args()

    start_year, end_year = args.years
    years = list(range(start_year, end_year + 1))

    print("Nice Weather — ERA5 Daily Statistics Downloader")
    print(f"Years: {start_year}–{end_year}  ({len(years)} years)")
    if args.cloud_mean:
        print("Mode: cloud mean upgrade (total_cloud_cover daily_mean only)")
        print("      Existing tmax/dew point data will NOT be modified.")
    else:
        print("Variables: 2m temperature, 2m dew point, total cloud cover (daily max)")
    print()

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    client = cdsapi.Client()
    failures = []

    for year in years:
        output_path = OUTPUT_ROOT / str(year) / "data.nc"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"── Year {year} ──────────────────────────────")

        if args.cloud_mean:
            success = download_cloud_mean_year(client, year, output_path)
        else:
            success = download_year(client, year, output_path)

        if not success:
            failures.append(year)
        print()

    # Summary
    print("── Summary ──────────────────────────────")
    print(f"Downloaded: {len(years) - len(failures)}/{len(years)} years")
    if failures:
        print(f"Failed: {', '.join(map(str, failures))}")
        flag = " --cloud-mean" if args.cloud_mean else ""
        print(f"\nRe-run: python scripts/download_era5_daily.py --years {min(failures)} {max(failures)}{flag}")
        sys.exit(1)
    else:
        print("All downloads successful! ✓")


if __name__ == "__main__":
    main()
