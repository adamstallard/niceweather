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
    tmax_f = pc.k_to_f(pc.TMAX_THRESHOLD_K)
    dew_f = pc.k_to_f(pc.DEWPOINT_THRESHOLD_K)
    check(f"tmax ≥ {tmax_f:.0f}°F", abs(pc.TMAX_THRESHOLD_K - 297.039) < 0.01)
    check(f"dew point < {dew_f:.0f}°F", abs(pc.DEWPOINT_THRESHOLD_K - 295.372) < 0.01)
    check(f"cloud cover < {pc.CLOUD_COVER_THRESHOLD * 100:.0f}% (daily max)",
          pc.CLOUD_COVER_THRESHOLD == 0.56, f"got {pc.CLOUD_COVER_THRESHOLD}")


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
    # Threshold boundaries: exactly 75°F passes, exactly 72°F dew fails
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


def test_per_year_path_equivalence():
    """
    The memory-bounded per-year path (build_perfect_mask_per_year +
    compute_probability_from_perfect) must produce output identical to the
    all-at-once path (concat all years → compute_probability_map).
    Uses tiny synthetic netCDF files in a temp dir, mimicking real ERA5
    layout: lat descending 90→-90, lon 0→360, 'valid_time' dim, leap year.
    """
    print("\n── Per-year path ≡ all-at-once path (synthetic netCDF) ──")
    import tempfile
    import xarray as xr
    import pandas as pd

    rng = np.random.default_rng(42)
    n_lat, n_lon = 5, 8
    lat = np.linspace(90, -90, n_lat)          # descending, like real ERA5
    lon = np.arange(0, 360, 360 / n_lon)       # 0–360, like real ERA5

    def make_year_ds(year, n_days):
        times = pd.date_range(f"{year}-01-01", periods=n_days, freq="D")
        shape = (n_days, n_lat, n_lon)
        # Values straddle all three thresholds so the mask is non-trivial
        t2m = rng.uniform(285, 310, shape).astype(np.float32)
        d2m = rng.uniform(280, 300, shape).astype(np.float32)
        tcc = rng.uniform(0, 1, shape).astype(np.float32)
        return xr.Dataset(
            {v: (("valid_time", "latitude", "longitude"), arr)
             for v, arr in [("t2m", t2m), ("d2m", d2m), ("tcc", tcc)]},
            coords={"valid_time": times, "latitude": lat, "longitude": lon},
        )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        datasets = {}
        for year, n_days in [(2023, 365), (2024, 366)]:  # includes leap year
            ydir = tmp_root / str(year)
            ydir.mkdir()
            ds = make_year_ds(year, n_days)
            ds.to_netcdf(ydir / "data.nc")
            datasets[year] = ds

        orig_root = pc.ERA5_DAILY
        pc.ERA5_DAILY = tmp_root
        try:
            pop = np.ones((n_lat, n_lon), dtype=bool)
            pop[0, 0] = False  # exercise the population mask too

            # New memory-bounded path (2025 requested but missing → skipped)
            perfect, doys = pc.build_perfect_mask_per_year([2023, 2024, 2025])
            prob_new = pc.compute_probability_from_perfect(perfect, doys, pop)

            # Old all-at-once path: concat → normalize → compute
            combined = xr.concat(
                [datasets[2023], datasets[2024]], dim="valid_time"
            ).rename({"valid_time": "time"})
            t_da = pc.normalize_grid(combined["t2m"])
            d_da = pc.normalize_grid(combined["d2m"])
            c_da = pc.normalize_grid(combined["tcc"])
            doys_old = pc.compute_calendar_day_index(t_da.time.values)
            # Both paths normalize the grid first, so the same pop mask
            # (indices in the normalized grid) applies to both
            prob_old = pc.compute_probability_map(
                t_da.values.astype(np.float32),
                d_da.values.astype(np.float32),
                c_da.values.astype(np.float32),
                doys_old, pop,
            )

            check("doys identical", np.array_equal(doys, doys_old))
            check("T dimension = 731 (365+366)", perfect.shape[0] == 731,
                  f"got {perfect.shape[0]}")
            check("probability maps identical",
                  np.array_equal(prob_new, prob_old),
                  f"max abs diff {np.abs(prob_new - prob_old).max()}")
            check("perfect mask is boolean (1 byte/obs)",
                  perfect.dtype == np.bool_, f"got {perfect.dtype}")
        finally:
            pc.ERA5_DAILY = orig_root


def test_multi_year_obs_counts():
    """
    Step 2: verify the observation pool size is correct when multiple years are
    concatenated.  Uses a small synthetic array to check analytically — no real
    data needed.
    """
    print("\n── Multi-year observation counts (synthetic) ──")
    import xarray as xr, pandas as pd

    def make_year(year_str, n_days):
        """Return a tiny (n_days, 1, 1) DataArray for the given year."""
        times = pd.date_range(year_str, periods=n_days, freq="D")
        return xr.DataArray(
            np.ones((n_days, 1, 1), dtype=np.float32),
            dims=("time", "latitude", "longitude"),
            coords={"time": times},
        )

    # Build 3 synthetic years: 365, 366 (leap), 365 days
    years_da = [make_year("2022-01-01", 365),
                make_year("2023-01-01", 366),
                make_year("2024-01-01", 365)]
    combined = xr.concat(years_da, dim="time")
    doys = pc.compute_calendar_day_index(combined.time.values)
    W = pc.WINDOW_DAYS

    def obs_in_window(cal_day):
        lo, hi = cal_day - W, cal_day + W
        if lo < 1 and hi > 365:
            return np.ones(len(doys), dtype=bool)
        elif lo < 1:
            return (doys <= hi) | (doys >= (365 + lo))
        elif hi > 365:
            return (doys >= lo) | (doys <= (hi - 365))
        else:
            return (doys >= lo) & (doys <= hi)

    n_years = len(years_da)
    expected = (2 * W + 1) * n_years  # 15 × 3 = 45
    # Check mid-year day (no wraparound) and year-end days
    for cal_day in [100, 182, 1, 365]:
        n_obs = obs_in_window(cal_day).sum()
        # Allow ±n_years tolerance for year-boundary edge cases
        ok = abs(n_obs - expected) <= n_years
        check(f"day {cal_day}: obs={n_obs} ≈ {expected} (±{n_years})", ok,
              f"got {n_obs}")


def test_multi_year_convergence():
    """
    Steps 3 & 4: load the current perfect_weather.bin (assumed to be from the
    most recently processed run) and check geographic/seasonal sanity.
    Skips gracefully if the binary is missing or is the synthetic one (< 1 MB).
    """
    print("\n── Multi-year geographic/seasonal sanity (real binary) ──")
    if not pc.OUTPUT_FILE.exists():
        print("  [SKIP] no perfect_weather.bin")
        return
    if pc.OUTPUT_FILE.stat().st_size < 1_000_000:
        print("  [SKIP] binary looks synthetic (< 1 MB)")
        return

    buf = pc.OUTPUT_FILE.read_bytes()
    n_cells, n_days, n_lat, n_lon = struct.unpack(">IHHH", buf[:10])
    lat_min, lat_max, lon_min, lon_max = struct.unpack(">ffff", buf[10:26])

    check("binary: lat ascending", lat_min < lat_max)
    check("binary: lon in [-180,180)", lon_min >= -180 and lon_max < 180)
    check("binary: n_cells plausible (1 k – 500 k)", 1_000 <= n_cells <= 500_000,
          f"got {n_cells:,}")

    # Parse all cells into a dict {(i_lat, i_lon): uint8 array[365]}
    cells = {}
    offset = 26
    for _ in range(n_cells):
        i_lat, i_lon = struct.unpack(">HH", buf[offset:offset + 4])
        probs = np.frombuffer(buf[offset + 4:offset + 4 + 365], dtype=np.uint8)
        cells[(i_lat, i_lon)] = probs
        offset += 369

    lat_res = (lat_max - lat_min) / (n_lat - 1)
    lon_res = (lon_max - lon_min) / (n_lon - 1)

    def lookup(target_lat, target_lon):
        i_lat = round((target_lat - lat_min) / lat_res)
        i_lon = round((target_lon - lon_min) / lon_res)
        # search ±2 cells in case of rounding
        for di in range(-2, 3):
            for dj in range(-2, 3):
                p = cells.get((i_lat + di, i_lon + dj))
                if p is not None:
                    return p
        return None

    def peak_day(probs):
        return int(np.argmax(probs)) + 1  # 1-based

    # --- Hemisphere seasonality ---
    # Northern mid-latitude: interior SoCal should peak May–Sep (days 121–273)
    p_socal = lookup(33.5, -116.5)
    if p_socal is not None and p_socal.max() > 0:
        pd_socal = peak_day(p_socal)
        check("SoCal peak in Northern summer (days 100–280)", 100 <= pd_socal <= 280,
              f"peak day {pd_socal}")
    else:
        print("  [INFO] SoCal not active — normal for ≤2 years with 30% cloud threshold")

    # Southern mid-latitude: Cape Town should peak Nov–Feb (days 305–365 or 1–59)
    p_cpt = lookup(-33.9, 18.4)
    if p_cpt is not None and p_cpt.max() > 0:
        pd_cpt = peak_day(p_cpt)
        in_sh_summer = pd_cpt >= 305 or pd_cpt <= 59
        check("Cape Town peak in Southern summer (Nov–Feb)", in_sh_summer,
              f"peak day {pd_cpt}")
    else:
        print("  [INFO] Cape Town not active — may need more years")

    # London: should remain dark (strict cloud + dew threshold)
    p_lon = lookup(51.5, -0.1)
    check("London has no active cell", p_lon is None or p_lon.max() == 0,
          f"max prob {p_lon.max() if p_lon is not None else 'N/A'}")

    # --- Smoothness: day-to-day jumps shrink as years are added ---
    # With N years the window has 15*N obs; a single day turning over changes
    # probability by at most 100/15 ≈ 7 pp per year boundary crossing.
    # In practice with 1 year jagged curves are normal; by 3+ years max jump
    # should be ≤ 20 pp.  We scale the tolerance so the test is meaningful at
    # every stage and tightens automatically as more years are loaded.
    n_years_approx = max(1, len(list(pc.ERA5_DAILY.glob("[0-9]*/data.nc"))))
    # Smoothness is only meaningfully enforced at 3+ years; with 1–2 years the
    # 15×N observation pool is too small to eliminate single-event spikes.
    p_phx = lookup(33.4, -112.1)
    if p_phx is not None and p_phx.max() > 0:
        diffs = np.abs(np.diff(p_phx.astype(np.int16)))
        max_jump = int(diffs.max())
        if n_years_approx < 3:
            print(f"  [INFO] Phoenix max jump {max_jump} pp "
                  f"(smoothness check skipped for {n_years_approx}-yr data — expected noise)")
        else:
            smooth_limit = max(20, round(800 / (15 * n_years_approx)))  # 24 @3yr, 20 @4yr+
            check(f"Phoenix curve smooth (max jump ≤ {smooth_limit} pp, {n_years_approx}-yr data)",
                  max_jump <= smooth_limit, f"max jump {max_jump} pp")

    # --- No-data in extreme polar regions (above 71°N / below 56°S after bundler crop) ---
    # These are clipped in bundle_web_data.py but the binary itself may still contain them;
    # the check is that any cell at lat > 72 is outside the populated band anyway.
    polar_cells = [(k, v) for k, v in cells.items()
                   if lat_min + k[0] * lat_res > 72.0]
    # Not a hard failure — just informational
    if polar_cells:
        print(f"  [INFO] {len(polar_cells)} cells above 72°N in binary "
              "(cropped by bundler, not rendered)")


def main() -> None:
    test_thresholds()
    test_doy_mapping()
    test_probability_math()
    test_normalize_grid()
    test_binary_roundtrip()
    test_population_mask()
    test_raw_data()
    test_per_year_path_equivalence()
    test_multi_year_obs_counts()
    test_multi_year_convergence()
    print(f"\n{'='*50}\nResults: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
