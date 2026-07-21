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
- [ ] Open `web/index.html` in browser and visually verify:
  - Heatmap continuous (no vertical gaps), aligned with boundaries at all latitudes
  - No land visible beyond −56°/+71°; panning stops hard at the band edges
  - Slider (with month labels), play animation, hue picker
  - Click a shaded cell → popup with probability, sparkline, "Best day" button
  - Click an empty cell → "No data here" message

### Generate Real Data (when ready)
- [x] Accept CDS license ✓
- [ ] Run `python3 scripts/download_era5_daily.py --years 2010 2024` (~1–2 days)
- [ ] Run `python3 scripts/download_worldpop.py` (~5 min)
- [ ] Run `python3 scripts/process_climate.py --calibrate-only`
- [ ] Run `python3 scripts/process_climate.py --years 2010 2024` (~30–60 min)
- [ ] Replace `data/processed/perfect_weather.bin` with generated file
