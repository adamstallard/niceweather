# Nice Weather — Task List

**Documentation Strategy**: Only use README.md (user-facing), spec.md (technical), and tasklist.md (tracking). No other markdown files. Keep them in sync as you work.

## Current Status & Plan

**Phase 1 (In Progress)**: Download multi-year base data (2022–2023 running; then 2010–2021). Uses `daily_maximum` for all variables. This gives us the population mask and basic structure working across years.

**Phase 2 (Queued)**: Secondary download of `daily_mean` cloud cover for all years (2010–2024). This will merge with existing data — no deletions. The downloader supports this by overwriting just the tcc variable in each year's data.nc.

**Phase 3 (Queued)**: Reprocess all years with new, refined thresholds:
- Max temp ≥ 75°F (unchanged)
- Max dew point < 72°F (was 68°F)
- **Mean cloud cover < 50%** (was daily_max < 56%) — this fixes Galapagos
- Population ≥ 2 (unchanged)

## ✅ Completed
- [x] Algorithm & architecture finalized
- [x] Data downloader scripts (month-by-month to avoid API limits)
- [x] Processing pipeline (binary format, population masking, etc.)
- [x] Web UI with Leaflet.js, day slider, play animation
- [x] Synthetic test data (7.6 MB, structurally identical to real data)
- [x] Heatmap: single hue (amber), opacity = probability (<50% hidden, 50% → 0.1, 100% → 0.8)
- [x] Compact legend (gradient bar, 50%–100% labels)
- [x] Offline map: Natural Earth 50m GeoJSON boundaries (countries + state lines)
- [x] Vendored Leaflet JS/CSS locally (web/vendor/) — no CDN or tile server needed
- [x] Cloud cover threshold changed 50% → 30% (spec, README, footer)
- [x] Fixed canvas latitude flip (lat_idx 0 = south, canvas y=0 = north)
- [x] **Self-contained offline distribution**: All data bundled in `web/data.js` (base64 binary + GeoJSON globals)
- [x] **Zero dependencies for end user**: Open `web/index.html` directly in browser, no server/Python needed
- [x] **Bundling pipeline**: `generate_synthetic_bin.py` now calls `bundle_web_data.py` automatically
- [x] Hue picker (6 swatches) with dynamic legend
- [x] **Latitude crop −56°/+71°**: boundaries clipped in bundler, hard pan bounds (`maxBoundsViscosity`), `fitBounds` + dynamic `minZoom`
- [x] **Fixed vertical stripe bug**: synthetic generator emitted only every 3rd longitude; data now continuous
- [x] **Fixed heatmap/map misalignment**: canvas rows now positioned in Mercator space (was equirectangular, misaligned at mid-latitudes)
- [x] **Click to inspect**: popup with day probability, 365-day sparkline, "Best day" jump button; graceful no-data message
- [x] Slider month tick labels (Jan–Dec); slider defaults to today's day-of-year

## 📋 To Do

### QA
- [x] Open `web/index.html` in browser and visually verify:
  - Heatmap continuous (no vertical gaps), aligned with boundaries at all latitudes
  - No land visible beyond −56°/+71°; panning stops hard at the band edges
  - Slider (with month labels), play animation, hue picker
  - Click a shaded cell → popup with probability, sparkline, "Best day" button
  - Click an empty cell → "No data here" message

### Data Processing Verification (run `python3 scripts/test_processing.py`)
Raw data integrity (per downloaded year):
- [x] `data.nc` opens; contains all 3 variables (t2m, d2m, tcc)
- [x] Single time dimension (`valid_time`) with 365/366 daily steps, no NaN padding
- [x] Grid is 721×1440 (0.25°); lat spans 90→−90, lon spans 0→359.75
- [x] Value sanity: t2m/d2m in 180–340 K, tcc in 0–1, d2m ≤ t2m nearly everywhere

Processing logic (unit tests, synthetic inputs):
- [ ] Day-of-year mapping: Feb 29 → slot 59, Dec 31 (leap) → slot 365
- [ ] Moving window: correct ±7-day selection incl. year-end wraparound (day 1, day 365)
- [ ] Probability math: known synthetic inputs → exact expected probabilities
- [ ] Thresholds match spec: ≥75°F, <60°F dew point, <30% cloud
- [ ] Population mask: True over a known city, False over open ocean

Output contract (must match `web/app.js` parser):
- [ ] Binary roundtrip: write small grid → parse header + cells → values identical
- [ ] Header big-endian; file size = 26 + n_cells × 369 bytes
- [ ] `lat_min < lat_max` in header (lat ascending; latIdx 0 = south, as web expects)
- [ ] `lon_min ≈ −180, lon_max < 180` (web wraps clicks to [−180, 180))
- [ ] Cells below 50% cutoff stored as 0

End-to-end (real 2024 data):
- [ ] `--calibrate-only` report plausible (Phoenix summer high, London low, Honolulu humid-capped)
- [ ] Full run completes; active cell count plausible; spot-check known cities in binary
- [ ] Bundle via `bundle_web_data.py`; visual check in browser

### Multi-year verification (run after adding each new year)

The core question: are the years being correctly pooled — no duplicate days, no dropped
days, no year dominating — and do the resulting probabilities behave as expected?

**Step 1 — Raw data: confirm each year file is independently clean**
Run `python3 scripts/test_processing.py` after every new year download.
The raw-data section already checks all three.  Any FAIL before processing = bad download.

**Step 2 — Observation-count sanity (`scripts/test_processing.py` multi-year section)**
For each calendar day d (1–365) the window should contain exactly
`(2 × WINDOW_DAYS + 1) × n_years` observations (±1 at year-ends due to wraparound
with non-full windows).  The test verifies this analytically with a small synthetic
multi-year array so we know the concat is producing the right pool size.

**Step 3 — Convergence / smoothness check (automated, in test script)**
Run process_climate.py twice: once with just 2024, once with 2024+new year.
Extract the per-cell probability curves for 5 calibration cities and verify:
- Active cell count grows or stays the same (never shrinks — more data only opens cells)
- Phoenix AZ: peak probability stays within ±15 pp of the 2024 baseline (80%)
- Phoenix AZ: curve shape is smooth (no single-day spikes > 20 pp above neighbours)
- Southern-Hemisphere city (e.g. Cape Town −33.9,18.4): peak shifts toward Jan/Feb
  (Northern-Hemisphere summer = Southern winter, so peak moves to Dec–Feb calendar days)
- London UK: remains at 0 active cells (strict cloud threshold, consistent year to year)

**Step 4 — Hemisphere seasonality check (automated)**
For a set of known locations in each hemisphere, verify the peak calendar day falls in the
expected season:
- Northern mid-latitudes (>25°N): peak in days 120–270 (May–Sep) if an active cell exists
- Southern mid-latitudes (<−25°S): peak in days 1–59 or 300–365 (Nov–Feb) if active
- Equatorial band (±15°): peak can be anywhere, but variance across the year should be low

**Step 5 — No-data plausibility (manual spot check)**
After processing N ≥ 2 years, open the browser and check three things:
- Slider on day 1 (Jan 1): Southern Africa, southern South America, and Australia are lit;
  northern Europe, UK, eastern USA are dark. The opposite should be true on day 182.
- The pattern animates smoothly day-to-day (no flickering from noisy single-year data)
- The active-cell count printed by process_climate.py is within 10–30% of the 1-year count
  (large swing = suspect; identical = also suspect since more years should open new marginal cells)

**When to escalate**
If Step 3 shows Phoenix probability changes by > 30 pp from 2024 baseline, or Step 4 shows
a hemisphere check failing, re-examine the year's raw data with the calibration report
before adding further years.

### Known Issues (resolved 2026-07-21)
- [x] `download_era5_daily.py`: now extracts all .nc files per ZIP and merges; concat uses `valid_time`
- [x] `process_climate.py`: cloud threshold → 0.3; lat/lon normalized before writing; `valid_time` handled
- [x] 2024 re-downloaded with fixed script (1.5 GB, all 3 variables, 366 days) ✓

### Generate Real Data — Phase 1: Multi-year Base Data
- [x] Accept CDS license ✓
- [x] Run `python3 scripts/download_worldpop.py` ✓ (829 MB)
- [x] Re-run `python3 scripts/download_era5_daily.py --years 2024 2024` ✓ (1.5 GB)
- [x] Run `python3 scripts/process_climate.py --years 2024 2024` ✓ (55,268 cells, 19.4 MB)
- [x] Visual check with 1-year data ✓
- [/] Download 2022–2023: `python3 scripts/download_era5_daily.py --years 2022 2023` **(in progress)**
- [ ] Verify 2022–2023 files exist and are valid (check `data/raw/era5_daily/2022/data.nc` and `2023/data.nc`)
- [ ] Run tests after download: `python3 scripts/test_processing.py`
- [ ] Run `python3 scripts/process_climate.py --calibrate-only --years 2022 2024`
- [ ] Run `python3 scripts/process_climate.py --years 2022 2024`
- [ ] Run tests on multi-year output; visual check — confirm smoothing + SH seasonality
- [ ] If tests pass: download remaining years `--years 2010 2021`
- [ ] Download 2010–2021 data (keep existing files; do NOT delete)

### Generate Real Data — Phase 2: Mean Cloud Cover (Galapagos fix)
After Phase 1 complete, reprocess with improved thresholds and daily mean cloud cover:

- [ ] **Download daily_mean cloud cover for all years (2010–2024)**
  - Modify downloader to request `daily_mean` for `total_cloud_cover` only
  - Keep temp/dew point as `daily_maximum` (unchanged)
  - Run: `python3 scripts/download_era5_daily.py --years 2010 2024 --cloud-statistic daily_mean`
  - **Important**: Files will merge with existing data.nc files (xarray overwrites just the tcc variable)
  - Existing monthly files are NOT deleted — secondary download adds only the cloud cover data
- [ ] Run `python3 scripts/process_climate.py --calibrate-only --years 2010 2024`
- [ ] **Final reprocess with new thresholds**:
  - Max temperature: ≥ 75°F (unchanged)
  - Max dew point: < 72°F (was 68°F — matches tropical comfort)
  - **Mean cloud cover: < 50%** (was daily_max < 56%)
  - Population cutoff: ≥ 2 (unchanged)
- [ ] Run `python3 scripts/process_climate.py --years 2010 2024`
- [ ] Run tests on final multi-year output; visual check
- [ ] Verify Galapagos now shows activity in best months (Nov–Dec should peak with mean cloud metric)
- [ ] Final `python3 scripts/bundle_web_data.py` + visual sign-off
