# Nice Weather 🌤️

An interactive world map showing where on Earth has the highest probability of **"perfect" weather** on any given day of the year. Slide through a day-of-year timeline and watch the map update to reveal where the conditions are most likely to be ideal.

## What is a "Perfect Day"?

All four conditions must be met:

| Condition | Threshold |
|---|---|
| Maximum temperature | ≥ 75°F (23.9°C) |
| Precipitation | < 0.5 mm |
| Sunshine | High surface solar radiation (mostly sunny proxy) |
| Humidity | Dew point < 60°F (15.6°C) — not uncomfortably humid |

> Sunshine is measured using **surface downwelling shortwave radiation** (W/m²) from ERA5-Land, which captures what sunlight actually reaches the surface — a more accurate proxy for "mostly sunny" than cloud cover percentages.

## Features

- **Interactive World Map** — Clean Natural Earth basemap with country boundaries and key city labels
- **Day-of-Year Slider** — Scrub through all 365 days to see the probability map shift globally
- **Color-Blind Friendly Shading** — Single amber/orange hue that contrasts clearly with both ocean blue and land green (accessible for red-green color-blind users)
- **Probability Shading** — Only areas with ≥ 50% probability are shown; opacity scales linearly from barely visible (50%) to nearly opaque (100%)
- **Populated Areas Only** — Cells with fewer than ~100 people (from WorldPop 2020) are excluded
- **Offline Capable** — All data is pre-processed into a single compact binary file loaded at startup

## How Probabilities Are Computed

For each 0.1° grid cell (~11 km) and each calendar day:

1. A **±7-day moving window** is applied around each calendar day across 30 years (1995–2024)
2. This yields ~450 observations per calendar day (15 days × 30 years), dramatically reducing noise from one-off anomalies
3. The fraction of observations meeting all four conditions = the probability
4. Cells below 50% or with insufficient population are excluded

## Data Sources

| Data | Source | Notes |
|---|---|---|
| Temperature, dew point, solar radiation | [ERA5-Land Daily Statistics](https://cds.climate.copernicus.eu/datasets/derived-era5-land-daily-statistics) | 0.1°, 1995–2024 |
| Precipitation | [ERA5-Land Hourly](https://cds.climate.copernicus.eu/datasets/reanalysis-era5-land) | Aggregated to daily totals |
| Population mask | [WorldPop 2020](https://www.worldpop.org/) | 1km global, resampled to ERA5 grid |
| Base map | [Natural Earth](https://www.naturalearthdata.com/) | 1:50m raster + vectors |

## Project Structure

```
niceweather/
├── data/                    # NOT in git — raw and processed data files
│   ├── raw/
│   │   ├── era5_daily/      # ERA5 daily stats by year (tmax, dewpoint, solar)
│   │   ├── era5_precip/     # ERA5 hourly precip aggregated to daily
│   │   └── worldpop/        # WorldPop population GeoTIFF
│   └── processed/
│       └── perfect_weather.bin  # Final compact data for the web app
├── scripts/                 # IN git — all data processing scripts
│   ├── download_era5_daily.py   # Download temperature, dew point, solar radiation
│   ├── download_era5_precip.py  # Download & aggregate precipitation
│   ├── download_worldpop.py     # Download WorldPop population mask
│   ├── process_climate.py       # Compute per-cell daily probabilities (coming soon)
│   └── requirements.txt
├── web/                     # IN git — the interactive web app (coming soon)
│   ├── index.html
│   ├── app.js
│   └── style.css
└── spec.md                  # Full project specification and decisions log
```

## Getting Started (Data Pipeline)

### 1. Prerequisites

- Python 3.10+
- A free [Copernicus Climate Data Store (CDS)](https://cds.climate.copernicus.eu/) account
- Your CDS API key in `~/.cdsapirc`:
  ```
  url: https://cds.climate.copernicus.eu/api
  key: <your-api-key>
  ```

### 2. Install dependencies

```bash
pip install -r scripts/requirements.txt
```

### 3. Download the data

```bash
# ERA5 daily stats: temperature, dew point, solar radiation (1995–2024)
python scripts/download_era5_daily.py

# ERA5 hourly precipitation, aggregated to daily totals (1995–2024)
python scripts/download_era5_precip.py

# WorldPop 2020 global population mask
python scripts/download_worldpop.py
```

All download scripts support `--resume` (default: on) and `--years START END` to download a subset.

> **Note**: The full dataset is large (~hundreds of GB). Downloads resume automatically if interrupted.

## License

Data sources are used under their respective open licenses:
- ERA5-Land: [Copernicus License](https://cds.climate.copernicus.eu/api/v2/terms/static/licence-to-use-copernicus-products.pdf)
- WorldPop: [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)
- Natural Earth: Public Domain
