# Nice Weather — Task List

**Documentation Strategy**: Only use README.md (user-facing), spec.md (technical), and tasklist.md (tracking). No other markdown files. Keep them in sync as you work.

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
- [ ] `data.nc` opens; contains all 3 variables (t2m, d2m, tcc)
- [ ] Single time dimension (`valid_time`) with 365/366 daily steps, no NaN padding
- [ ] Grid is 721×1440 (0.25°); lat spans 90→−90, lon spans 0→359.75
- [ ] Value sanity: t2m/d2m in 180–340 K, tcc in 0–1, d2m ≤ t2m nearly everywhere

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

### Known Issues (found 2026-07-21, fix before re-download)
- [ ] `download_era5_daily.py`: extracts only first .nc from CDS ZIP → 2024 file has only d2m; concat uses wrong dim (`time` vs `valid_time`) → NaN-padded 12×366 structure
- [ ] `process_climate.py`: cloud threshold 0.5 ≠ spec 0.3; lat written descending (header lat_min=90) breaks web renderer; lon 0–360 not converted to −180..180; doys read `.time` not `valid_time`
- [ ] 2024 raw data unusable → re-download required after fixes

### Generate Real Data (when ready)
- [x] Accept CDS license ✓
- [x] Run `python3 scripts/download_worldpop.py` (~5 min) ✓ (829 MB)
- [ ] Re-run `python3 scripts/download_era5_daily.py --years 2024 2024` (after fixes)
- [ ] Run `python3 scripts/download_era5_daily.py --years 2010 2023` (~1–2 days)
- [ ] Run `python3 scripts/process_climate.py --calibrate-only`
- [ ] Run `python3 scripts/process_climate.py --years 2010 2024` (~30–60 min)
- [ ] Replace `data/processed/perfect_weather.bin` with generated file
