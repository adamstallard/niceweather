#!/usr/bin/env python3
"""
test_processing.py

Verification suite for the perfect-weather data pipeline (see tasklist.md
"Data Processing Verification"). Runs:

  1. Unit tests on process_climate.py logic (synthetic inputs)
  2. Output-contract tests (binary format must match web/app.js parser)
  3. Raw-data integrity checks on any downloaded ERA5 year files

Usage:  python3 scripts/test_processing.py
Exit code 0 = all pass.
"""

import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import process_climate as pc

PASS, FAIL = 0, 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}  {detail}")


# ---------------------------------------------------------------------------
# 1. Unit tests — processing logic
# ---------------------------------------------------------------------------


def test_thresholds():
    print("\n── Thresholds match spec ──")
    check("tmax ≥ 75°F", abs(pc.TMAX_THRESHOLD_K - 297.039) < 0.01)
    check("dew point < 60°F", abs(pc.DEWPOINT_THRESHOLD_K - 288.706) < 0.01)
    check("cloud cover < 30%", pc.CLOUD_COVER_THRESHOLD == 0.3,
          f"got {pc.CLOUD_COVER_THRESHOLD}")


def test_doy_mapping():
    print("\n── Day-of-year mapping (leap handling) ──")
    times = np.array([
        "2024-01-01", "2024-02-28", "2024-02-29", "2024-03-01",
        "2024-12-31", "2023-12-31",
    ], dtype="datetime64[ns]")
    doys = pc.compute_calendar_day_index(times)
    check("Jan 1 → 1", doys[0] == 1, f"got {doys[0]}")
    check("Feb 28 (leap) → 59", doys[1] == 59, f"got {doys[1]}")
    check("Feb 29 → 59 (clamped)", doys[2] == 59, f"got {doys[2]}")
    check("Mar 1 (leap) → 61→? stays ≤365", doys[3] in (60, 61), f"got {doys[3]}")
    check("Dec 31 (leap, 366) → 365", doys[4] == 365, f"got {doys[4]}")
    check("Dec 31 (non-leap) → 365", doys[5] == 365, f"got {doys[5]}")


def test_probability_math():
    print("\n── Probability computation (synthetic) ──")
    # 30 synthetic days all mapped to doy 100; 1 cell grid
    T = 30
    doys = np.full(T, 100, dtype=np.int16)
    shape = (T, 1, 1)
    tmax = np.full(shape, 300.0, dtype=np.float32)      # hot enough
    dew = np.full(shape, 280.0, dtype=np.float32)       # dry enough
    cloud = np.full(shape, 0.1, dtype=np.float32)       # sunny
    # Make 12 of 30 days fail (cloudy) → prob = 18/30 = 0.6
    cloud[:12] = 0.9
    pop = np.ones((1, 1), dtype=bool)
    prob = pc.compute_probability_map(tmax, dew, cloud, doys, pop)
    check("day-100 prob = 0.6", abs(prob[0, 0, 99] - 0.6) < 1e-6,
          f"got {prob[0, 0, 99]}")
    check("window: day 93 includes doy 100", abs(prob[0, 0, 92] - 0.6) < 1e-6)
    check("outside window (day 80) = 0", prob[0, 0, 79] == 0.0)
    # Year-end wraparound: obs at doy 363 must count toward day 3 (±7)
    doys2 = np.full(T, 363, dtype=np.int16)
    cloud2 = np.full(shape, 0.1, dtype=np.float32)
    prob2 = pc.compute_probability_map(tmax, dew, cloud2, doys2, pop)
    check("wraparound: doy 363 counts for day 3", prob2[0, 0, 2] == 1.0,
          f"got {prob2[0, 0, 2]}")
    check("wraparound: doy 363 counts for day 365", prob2[0, 0, 364] == 1.0)
    # Population mask zeroes cells
    prob3 = pc.compute_probability_map(
        tmax, dew, cloud2, doys2, np.zeros((1, 1), dtype=bool))
    check("pop mask zeroes cell", prob3.max() == 0.0)
    # Threshold boundaries: exactly 75°F passes, exactly 60°F dew fails
    tmax_b = np.full(shape, pc.TMAX_THRESHOLD_K, dtype=np.float32)
    dew_b = np.full(shape, pc.DEWPOINT_THRESHOLD_K, dtype=np.float32)
    prob_b = pc.compute_probability_map(tmax_b, dew_b, cloud2, doys2, pop)
    check("dew = threshold → not perfect", prob_b.max() == 0.0)


def test_binary_roundtrip():
    print("\n── Binary output contract (web/app.js parser) ──")
    # Small synthetic grid: 3 lat × 4 lon, ascending lat, lon in [-180,180)
    n_lat, n_lon = 3, 4
    lat = np.array([10.0, 10.25, 10.5])
    lon = np.array([-20.0, -19.75, -19.5, -19.25])
    prob = np.zeros((n_lat, n_lon, 365), dtype=np.float32)
    prob[1, 2, :] = 0.75      # one active cell, all days 75%
    prob[0, 0, 5] = 0.40      # below cutoff → excluded entirely
    out = pc.OUTPUT_FILE
    backup = out.read_bytes() if out.exists() else None
    try:
        pc.write_output(prob, lat, lon)
        buf = out.read_bytes()
        n_cells, n_days, h_lat, h_lon = struct.unpack(">IHHH", buf[:10])
        lat_min, lat_max, lon_min, lon_max = struct.unpack(">ffff", buf[10:26])
        check("n_cells = 1", n_cells == 1, f"got {n_cells}")
        check("n_days = 365", n_days == 365)
        check("grid dims", (h_lat, h_lon) == (3, 4))
        check("lat_min < lat_max (ascending)", lat_min < lat_max,
              f"{lat_min} vs {lat_max}")
        check("lat bounds", abs(lat_min - 10.0) < 1e-4 and abs(lat_max - 10.5) < 1e-4)
        check("lon bounds", abs(lon_min - (-20.0)) < 1e-4)
        check("file size = 26 + n×369", len(buf) == 26 + n_cells * 369,
              f"got {len(buf)}")
        i_lat, i_lon = struct.unpack(">HH", buf[26:30])
        check("cell index (1,2)", (i_lat, i_lon) == (1, 2), f"got {(i_lat, i_lon)}")
        probs = np.frombuffer(buf[30:30 + 365], dtype=np.uint8)
        check("cell probs = 75", np.all(probs == 75), f"got {probs[:5]}")
    finally:
        if backup is not None:
            out.write_bytes(backup)
        elif out.exists():
            out.unlink()
    check("original bin restored", backup is None or out.read_bytes() == backup)


def test_normalize_grid():
    print("\n── Grid normalization (ERA5 → web convention) ──")
    import xarray as xr
    # Mimic real ERA5: lat 90→-90 descending, lon 0→359.75
    lat = np.linspace(90, -90, 19)
    lon = np.arange(0, 360, 20.0)
    data = np.random.rand(2, 19, 18).astype(np.float32)
    da = xr.DataArray(data, dims=("time", "latitude", "longitude"),
                      coords={"latitude": lat, "longitude": lon})
    # Track a known value: lat=90 (idx 0), lon=200 (idx 10)
    marker = float(da.isel(time=0).sel(latitude=90, longitude=200))
    norm = pc.normalize_grid(da)
    nlat, nlon = norm.latitude.values, norm.longitude.values
    check("lat ascending", nlat[0] < nlat[-1], f"{nlat[0]}..{nlat[-1]}")
    check("lon in [-180, 180)", nlon.min() >= -180 and nlon.max() < 180)
    check("lon ascending", np.all(np.diff(nlon) > 0))
    check("values follow coords",
          float(norm.isel(time=0).sel(latitude=90, longitude=-160)) == marker)


def test_population_mask():
    print("\n── Population mask (WorldPop, real file) ──")
    if not pc.WORLDPOP_PATH.exists():
        print("  [SKIP] WorldPop file not present")
        return
    # Small ascending-lat grid over NYC and one over open South Pacific
    def make_grid(lat0, lon0):
        return (np.arange(lat0, lat0 + 1.0, 0.25),
                np.arange(lon0, lon0 + 1.0, 0.25))
    lat, lon = make_grid(40.25, -74.5)   # NYC area
    mask_nyc = pc.build_population_mask(lat, lon)
    check("NYC cells populated", mask_nyc.any(), "no populated cells found")
    # NYC is at grid north-east corner region; verify orientation:
    # lat 40.7 (Manhattan) is index 1-2 in ascending grid, must be True
    ilat = int(np.argmin(np.abs(lat - 40.75)))
    ilon = int(np.argmin(np.abs(lon - (-74.0))))
    check("Manhattan cell True (ascending-lat orientation)",
          bool(mask_nyc[ilat, ilon]))
    lat_o, lon_o = make_grid(-40.0, -130.0)  # open South Pacific
    mask_ocean = pc.build_population_mask(lat_o, lon_o)
    check("open ocean unpopulated", not mask_ocean.any(),
          f"{mask_ocean.sum()} cells populated")


def test_raw_data():
    print("\n── Raw ERA5 data integrity ──")
    import xarray as xr
    year_dirs = sorted(p for p in pc.ERA5_DAILY.glob("[0-9]*") if p.is_dir())
    if not year_dirs:
        print("  [SKIP] no downloaded years")
        return
    for ydir in year_dirs:
        path = ydir / "data.nc"
        if not path.exists():
            print(f"  [SKIP] {ydir.name}: no data.nc")
            continue
        ds = xr.open_dataset(path, engine="netcdf4")
        y = ydir.name
        have = set(ds.data_vars)
        check(f"{y}: has t2m/d2m/tcc", {"t2m", "d2m", "tcc"} <= have,
              f"got {sorted(have)}")
        tdim = "valid_time" if "valid_time" in ds.dims else "time"
        n_t = ds.sizes.get(tdim, 0)
        extra_dims = set(ds.dims) - {tdim, "latitude", "longitude"}
        check(f"{y}: single daily time dim (365/366)",
              n_t in (365, 366) and not extra_dims,
              f"dims={dict(ds.sizes)}")
        check(f"{y}: grid 721×1440",
              ds.sizes.get("latitude") == 721 and ds.sizes.get("longitude") == 1440)
        # Value sanity on a small sample (avoid loading 18 GB)
        if {"t2m", "d2m", "tcc"} <= have and n_t in (365, 366):
            sel = {tdim: slice(0, 5)}
            t = ds["t2m"].isel(**sel).values
            d = ds["d2m"].isel(**sel).values
            c = ds["tcc"].isel(**sel).values
            check(f"{y}: no NaNs in sample",
                  not (np.isnan(t).any() or np.isnan(d).any() or np.isnan(c).any()))
            check(f"{y}: t2m in 180–340 K", 180 < np.nanmin(t) and np.nanmax(t) < 340,
                  f"range {np.nanmin(t):.1f}–{np.nanmax(t):.1f}")
            check(f"{y}: tcc in 0–1", np.nanmin(c) >= 0 and np.nanmax(c) <= 1.001,
                  f"range {np.nanmin(c):.3f}–{np.nanmax(c):.3f}")
            check(f"{y}: d2m ≤ t2m (≥99% of cells)",
                  np.mean(d <= t + 0.5) > 0.99, f"{np.mean(d <= t + 0.5):.3f}")
        ds.close()


def main() -> None:
    test_thresholds()
    test_doy_mapping()
    test_probability_math()
    test_normalize_grid()
    test_binary_roundtrip()
    test_population_mask()
    test_raw_data()
    print(f"\n{'='*50}\nResults: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
