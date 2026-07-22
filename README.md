# Nice Weather 🌤️

An interactive world map showing where on Earth has the highest probability of **"perfect" weather** on any given day of the year. Slide through a day-of-year timeline and watch the map update to reveal where the conditions are most likely to be ideal.

## What is a "Perfect Day"?

All three conditions must be met:

| Condition | Threshold |
|---|---|
| Temperature | ≥ 75°F (23.9°C) |
| Humidity | Dew point < 72°F (22.2°C) |
| Sunshine | Cloud cover < 56% (daily max) |

## Features

- **Interactive World Map** — Natural Earth country and state/province boundaries (vector, offline), cropped to −56°/+71° latitude (no Antarctica, minimal polar distortion)
- **Day-of-Year Slider** — Scrub through all 365 days (month labels, defaults to today) to see perfect weather migrate globally
- **Click to Inspect** — Click anywhere to see that cell's probability, a full-year sparkline, and a "Best day" button that jumps to its peak day
- **Play Animation** — Watch the entire year animate smoothly, showing seasonal migration
- **Single Hue with Transparency** — Purple shading (user-selectable hue) where opacity = probability: below 50% is hidden, 50% is barely visible, 100% is mostly opaque (highest contrast, color-blind accessible)
- **Populated Areas Only** — Cells with fewer than ~100 people (WorldPop 2020) are excluded
- **Fast Loading** — All data pre-processed into compact binary file
- **Fully Offline** — Leaflet is vendored locally and boundaries are GeoJSON files in `web/data/`; no tile server or internet needed

The boundary GeoJSON files are committed to the repo. To re-download them:

```bash
python3 scripts/download_natural_earth.py
```

## How Probabilities Are Computed

For each 0.1° grid cell (~11 km) and each calendar day:

1. A **±7-day moving window** is applied around each calendar day across 15 years (2010–2024)
2. This yields ~225 observations per calendar day (15 days × 15 years), reducing noise from anomalies
3. The fraction of observations meeting all three conditions = the probability
4. Cells below 50% or with insufficient population are excluded

## Data Sources

| Data | Source | Notes |
|---|---|---|
| Temperature, dew point, cloud cover | [ERA5 Daily Statistics](https://cds.climate.copernicus.eu/datasets/derived-era5-single-levels-daily-statistics) | 0.1° resolution, 2010–2024 |
| Population mask | [WorldPop 2020](https://www.worldpop.org/) | 1km global, resampled to ERA5 grid |
| Political boundaries | [Natural Earth](https://www.naturalearthdata.com/) | 50m GeoJSON, bundled for offline use |

## Quick Start (Users)

**No dependencies, no server, fully offline:**

1. Open `web/index.html` in your browser (double-click or drag to browser)

That's it! The app is self-contained. All data (weather + boundaries) is bundled in `web/data.js`.

Use the **slider** to explore any day of the year, or click **Play** to animate through all 365 days and watch perfect weather migrate across the globe with the seasons.

## Project Structure

```
niceweather/
├── data/
│   ├── processed/
│   │   └── perfect_weather.bin  # Climate binary (7.6 MB) → bundled into web/data.js
│   └── raw/                     # (ERA5 downloads go here when generated)
├── scripts/
│   ├── download_era5_daily.py   # Fetch ERA5 climate data
│   ├── download_worldpop.py     # Fetch population mask
│   ├── download_natural_earth.py # Fetch boundary GeoJSON
│   ├── process_climate.py       # Compute probabilities → binary
│   ├── generate_synthetic_bin.py # Generate test data (auto-bundles)
│   ├── bundle_web_data.py       # Manual bundler (binary + boundaries → web/data.js)
│   └── requirements.txt
├── web/                         # Distribution folder (users get this)
│   ├── index.html               # Entry point
│   ├── app.js                   # Main app (reads from globals)
│   ├── style.css                # Styles
│   ├── data.js                  # Auto-generated: 14 MB bundle (all data)
│   ├── vendor/                  # Leaflet JS/CSS (offline)
│   └── data/                    # Source GeoJSON (not needed for users)
├── README.md                    # This file
├── spec.md                      # Algorithm & technical spec
└── tasklist.md                  # Progress tracking
```

## For Developers: Regenerating Data from ERA5

### Prerequisites

- Python 3.10+
- Free [Copernicus CDS](https://cds.climate.copernicus.eu/) account
- **Accept license**: https://cds.climate.copernicus.eu/datasets/derived-era5-single-levels-daily-statistics (click "Download" tab, then "Manage licences")
- CDS API key in `~/.cdsapirc`:
  ```
  url: https://cds.climate.copernicus.eu/api
  key: <your-api-key>
  ```

### Workflow

1. **Download and process climate data:**
   ```bash
   pip install -r scripts/requirements.txt
   python3 scripts/download_era5_daily.py --years 2010 2024
   python3 scripts/download_worldpop.py
   python3 scripts/process_climate.py --calibrate-only
   python3 scripts/process_climate.py --years 2010 2024
   ```
   This outputs `data/processed/perfect_weather.bin` (7.6 MB).

2. **Bundle for web app:**
   ```bash
   python3 scripts/generate_synthetic_bin.py
   # OR manually:
   python3 scripts/bundle_web_data.py
   ```
   This creates `web/data.js` (14 MB, contains binary + boundaries).

3. **Distribute:** Users get the `web/` folder — they just open `index.html`.

## License

Data sources are used under their respective open licenses:
- ERA5-Land: [Copernicus License](https://cds.climate.copernicus.eu/api/v2/terms/static/licence-to-use-copernicus-products.pdf)
- WorldPop: [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)
- Natural Earth: Public Domain
