#!/usr/bin/env python3
"""
download_natural_earth.py

Downloads Natural Earth political boundaries (public domain) as GeoJSON
for offline use by the web app. Saved to web/data/.

Source: nvkelso/natural-earth-vector GitHub repo (official Natural Earth mirror).
50m resolution is a good balance of detail vs. file size for a world map.
"""

import ssl
import urllib.request
from pathlib import Path

try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()

BASE = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson"

DATASETS = {
    "countries.geojson": f"{BASE}/ne_50m_admin_0_countries.geojson",
    "states.geojson": f"{BASE}/ne_50m_admin_1_states_provinces_lines.geojson",
}

WEB_DATA_DIR = Path("web/data")


def main():
    WEB_DATA_DIR.mkdir(parents=True, exist_ok=True)

    for filename, url in DATASETS.items():
        dest = WEB_DATA_DIR / filename
        if dest.exists():
            print(f"✓ {dest} already exists ({dest.stat().st_size / 1_048_576:.1f} MB), skipping")
            continue

        print(f"Downloading {filename}...")
        with urllib.request.urlopen(url, context=SSL_CONTEXT) as resp:
            dest.write_bytes(resp.read())
        print(f"✓ Wrote {dest} ({dest.stat().st_size / 1_048_576:.1f} MB)")


if __name__ == "__main__":
    main()
