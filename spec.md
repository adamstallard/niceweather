# Nice Weather — Project Specification

## Vision

An interactive world map overlay showing which populated areas of the world have a high probability of "perfect" weather on any given day of the year. The user slides through a day-of-year timeline and watches the map update to reveal where on Earth is most likely to have ideal conditions.

---

## "Perfect Day" Definition

A day is considered **perfect** if all four conditions are met:

| Condition | Threshold | Variable Used |
|---|---|---|
| Max temperature | ≥ 75°F (≈ 23.9°C) | ERA5-Land daily max 2m temperature |
| No precipitation | < 0.5 mm | ERA5-Land hourly precip, aggregated |
| Mostly sunny | Solar radiation > threshold (TBD) | ERA5-Land daily mean surface downwelling shortwave radiation |
| Not uncomfortably humid | Dew point < 60°F (≈ 15.6°C) | ERA5-Land daily max 2m dew point temperature |

### Why solar radiation instead of cloud cover?
Solar radiation measures what sunlight actually reaches the surface. A hazy day and a cloudy day can look similar in cloud cover metrics, but very different in experienced sunshine. Solar radiation is a more physically meaningful proxy for "mostly sunny." A threshold for "mostly sunny" will be calibrated using known sunny locations (e.g. Phoenix in summer) vs. known cloudy ones (e.g. Seattle in winter).

---

## Data Sources

### 1. ERA5-Land Daily Statistics (primary weather data)
- **Source**: Copernicus Climate Data Store (CDS)
- **Dataset ID**: `derived-era5-land-daily-statistics`
- **Resolution**: ~0.1° × 0.1° (~11 km)
- **Coverage**: Global land areas
- **Period**: 1995–2024 (30 years)
- **Variables**: daily max 2m temperature, daily max 2m dew point, daily mean surface solar radiation downwards
- **Note**: Accumulated variables (precipitation) are intentionally excluded from this dataset

### 2. ERA5-Land Hourly (precipitation only)
- **Source**: Copernicus Climate Data Store (CDS)
- **Dataset ID**: `reanalysis-era5-land`
- **Variable**: `total_precipitation` (accumulated from 00:00 UTC; daily total = value at 23:00)
- **Note**: Correct aggregation = `.resample('1D').last()` × 1000 (m → mm). Do **not** sum hourly values as they are already cumulative within the day.

### 3. WorldPop Global Population (population mask)
- **Source**: WorldPop / Humanitarian Data Exchange
- **Resolution**: ~1 km (1km global mosaic)
- **Year**: 2020
- **Purpose**: Mask out areas with population < 100 per cell (scaled to ERA5 resolution)

### 4. Natural Earth (basemap)
- **Source**: naturalearthdata.com
- **Products**: 1:50m raster base + country boundaries + populated places
- **Purpose**: Clean, visually readable base map; country labels and key city names

---

## Probability Model

For each ERA5-Land grid cell and each calendar day (1–365):

1. Use a **±7 day moving window** around each calendar day across all 30 years
   - e.g., for April 17: use April 10–24 for all years 1995–2024
   - This gives 15 days × 30 years = **450 observations** per calendar day
   - Reduces noise from one-off anomaly events
   - Produces a smoothly animated map as you slide between days
2. Count how many of those 450 observations meet all four "perfect day" criteria
3. Divide by 450 → **probability score** (0.0–1.0)
4. Discard all grid cells where probability < 0.50
5. Also discard all grid cells where population < threshold (~100 people)

---

## Output Data Format

A compact binary or JSON file (target: < 50 MB) containing for each grid cell:
- Latitude, longitude (or grid index)
- Array of 365 probability values (float16 or uint8)
- Only cells where at least one day has probability ≥ 0.50

This file is the only data file loaded by the web app (offline-capable after first load).

**Note**: Raw ERA5 data (~hundreds of GB) is NOT checked into git. Only the processing scripts and the final output file (if small enough) are tracked.

---

## Shading / Visual Design

- **Color**: Single hue that contrasts with both blue (ocean) and green (land)
  - Best candidate: **amber/orange** (e.g. HSL 35°) — clearly distinct from green and blue for red-green color-blind users
- **Opacity mapping**:
  - < 50% probability → not shown
  - 50% → barely visible (~10% opacity)
  - 100% → nearly opaque (~90% opacity)
  - Linear interpolation between those extremes
- Shading applied as a canvas overlay on the world map

---

## Interactive Map

- **Technology**: HTML + Vanilla JS + Canvas (offline-capable, no framework required)
- **Map base**: Natural Earth 1:50m raster (or Mapbox/Leaflet with offline tiles TBD)
- **Slider**: Day-of-year slider at the bottom (1–365), with month labels
- **Interaction**: Hover to show location name + probability score for that day
- **Animation**: Play button to animate through the full year

---

## Project File Structure

```
niceweather/
├── data/                    # NOT in git — raw and processed data
│   ├── raw/
│   │   ├── era5_daily/      # ERA5-Land Daily Statistics NetCDF files (by year)
│   │   ├── era5_precip/     # ERA5-Land hourly precip NetCDF files (by year)
│   │   └── worldpop/        # WorldPop GeoTIFF
│   └── processed/
│       └── perfect_weather.bin  # Final compact output for web app
├── scripts/                 # IN git — all processing scripts
│   ├── download_era5_daily.py   # Download ERA5 daily stats (temp, dewpoint, solar)
│   ├── download_era5_precip.py  # Download ERA5 hourly precip, aggregate to daily
│   ├── download_worldpop.py     # Download WorldPop population mask
│   ├── process_climate.py       # Compute per-cell daily probability scores
│   └── requirements.txt
├── web/                     # IN git — the interactive web app
│   ├── index.html
│   ├── app.js
│   └── style.css
├── spec.md                  # This file
└── README.md
```

---

## Open Questions / Future Decisions

1. **Solar radiation threshold**: What W/m² constitutes "mostly sunny"? Will calibrate against known reference locations.
2. **Final data file size**: Will the processed output fit in the repo (< 50 MB)? Depends on compression. May use uint8 (0–100) per cell per day with a lat/lon index.
3. **Map tile approach**: Pure offline raster vs. Leaflet with cached tiles?
4. **Leap years**: Day 366 can be handled by clamping to day 365 or ignoring Feb 29.
5. **CDS account**: User needs a CDS account and API key in `~/.cdsapirc` to run the download scripts.
