# Nice Weather — Task List

> **Docs**: README.md (user-facing) · spec.md (technical) · tasklist.md (this file). No other markdown files. Keep all three in sync.

---

## Roadmap

| Phase | What | Status |
|-------|------|--------|
| **1** | Download all years (2010–2024) with `daily_maximum` for all 3 variables | 🔄 In progress |
| **2** | Re-download all years with `daily_mean` cloud cover only; merge into existing files | ⏳ Queued |
| **3** | Reprocess with mean cloud cover threshold (< 50%); final bundle | ⏳ Queued |

**Current thresholds (Phase 1/interim):** Tmax ≥ 75 °F · Dew point < 72 °F · Cloud cover < 56% (daily max)
**Final thresholds (after Phase 2):** Tmax ≥ 75 °F · Dew point < 72 °F · Cloud cover < 50% (daily mean)

---

## Phase 1 — Download All Years (daily max, all variables)

Goal: build a complete 2010–2024 dataset using `daily_maximum` statistics for temperature, dew point, and cloud cover. Each year is stored in `data/raw/era5_daily/<year>/data.nc`.

### ✅ Done
- [x] CDS license accepted
- [x] WorldPop downloaded (`python3 scripts/download_worldpop.py` — 829 MB)
- [x] 2022 downloaded and verified (1.5 GB, 365 days, all 3 vars)
- [x] 2023 downloaded and verified (1.5 GB, 365 days, all 3 vars)
- [x] 2024 downloaded and verified (1.5 GB, 366 days, all 3 vars)
- [x] 3-year processing run (2022–2024): 84,408 active cells, 29.7 MB
- [x] 3-year test suite: 64/65 pass (Phoenix smoothness at 53 pp — expected, needs more years)
- [x] Bundle: `web/data.js` 43.2 MB

### 🔄 In Progress
- [/] Downloading 2010–2021: `python3 scripts/download_era5_daily.py --years 2010 2021` *(running — terminal 581540)*

### ⏳ After 2010–2021 download completes
- [ ] Run `python3 scripts/test_processing.py` — verify raw integrity for all new years
- [ ] Run `python3 scripts/process_climate.py --calibrate-only --years 2010 2024` — sanity-check calibration cities
- [ ] Run `python3 scripts/process_climate.py --years 2010 2024` — full 15-year processing
- [ ] Run `python3 scripts/test_processing.py` again — confirm Phoenix smoothness drops to ≤ 20 pp
- [ ] Run `python3 scripts/bundle_web_data.py` — rebuild `web/data.js`
- [ ] Visual check in browser (seasonal animation, hemisphere flip, no flickering)

---

## Phase 2 — Re-download Cloud Cover as Daily Mean

Once Phase 1 is complete, re-download **only** `total_cloud_cover` for all years using the `daily_mean` statistic. These files are merged into the existing `data.nc` files — temperature and dew point data are never re-downloaded or deleted.

**How it works (safe by design):**
- `--cloud-mean` downloads only `tcc` (daily_mean) month-by-month into `<year>/monthly_cloud_mean/` — a directory separate from `<year>/monthly/`
- The existing `<year>/monthly/*.nc` files (tmax + dew point) are **never touched**
- Each `<year>/data.nc` is updated atomically: old `tcc` variable is replaced with mean `tcc`; `t2m` and `d2m` are preserved unchanged
- Already-downloaded months are skipped on re-run (resume-safe)
- Requires Phase 1 `data.nc` to exist — will error if run first

### ⏳ Steps
- [ ] Run `python3 scripts/download_era5_daily.py --years 2010 2024 --cloud-mean`
- [ ] Run `python3 scripts/test_processing.py` — confirm each year's `data.nc` still has all 3 vars (t2m, d2m, new mean tcc)

---

## Phase 3 — Reprocess with Mean Cloud Cover

Once Phase 2 is complete, update the cloud threshold and reprocess everything to produce the final dataset.

**Why:** Daily-max cloud cover is pessimistic — a brief afternoon cloud can disqualify an otherwise sunny day. Daily-mean gives a truer picture. This is expected to unlock the Galápagos and similar locations.

### ⏳ Steps
- [ ] In `scripts/process_climate.py`, change `CLOUD_COVER_THRESHOLD = 0.56` → `0.50`
- [ ] Run `python3 scripts/process_climate.py --calibrate-only --years 2010 2024` — check Galápagos, Sahara, Canaries now look correct
- [ ] Run `python3 scripts/process_climate.py --years 2010 2024`
- [ ] Run `python3 scripts/test_processing.py` — all tests pass, Phoenix smooth
- [ ] Run `python3 scripts/bundle_web_data.py`
- [ ] Final visual sign-off: Galápagos shows activity in best months (Nov–Feb); seasonal animation smooth

---

## Reference

### Multi-year verification protocol

Run after processing any new batch of years to confirm years are being pooled correctly.

**Automated (`python3 scripts/test_processing.py`):**
- Raw integrity: each `data.nc` has t2m/d2m/tcc, correct grid (721×1440), no NaNs, values in range
- Observation counts: each calendar-day window = `(2 × 7 + 1) × n_years` observations (±1 at year-ends)
- Phoenix smoothness: max day-to-day jump ≤ 20 pp (enforced for ≥ 3 years)
- Geographic sanity: SoCal peak in May–Sep, Cape Town peak in Nov–Feb, London has no active cell

**Manual spot check (browser):**
- Day 1 (Jan 1): Southern Africa, Australia, southern South America lit; northern Europe dark
- Day 182 (Jul 1): opposite pattern
- Animation smooth (no day-to-day flickering)

**When to escalate:**
If Phoenix probability shifts > 30 pp from baseline, or hemisphere seasonality is wrong, inspect that year's raw data with `--calibrate-only` before continuing.

### Completed infrastructure
- [x] Algorithm & architecture finalized
- [x] Month-by-month downloader (avoids CDS API limits); resume-safe; atomic writes
- [x] Processing pipeline: sliding ±7-day window, population mask (WorldPop ≥ 2), binary output
- [x] Test suite: thresholds, day-of-year mapping, window logic, prob math, pop mask, binary contract, multi-year sanity
- [x] Web UI: Leaflet.js, day slider with month labels, play animation, hue picker, click-to-inspect sparkline
- [x] Self-contained offline bundle: `web/data.js` (base64 binary + GeoJSON); open `web/index.html` directly, no server needed
- [x] Latitude crop −56°/+71° (bundler clips GeoJSON; hard pan bounds in UI)
- [x] Fixed: canvas latitude flip, heatmap/Mercator alignment, vertical stripe bug
