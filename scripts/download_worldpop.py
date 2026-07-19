#!/usr/bin/env python3
"""
download_worldpop.py

Downloads the WorldPop 2020 Global Population Count mosaic at 1km resolution.
This is used to create a population mask, filtering out ERA5-Land grid cells
with fewer than ~100 people (scaled appropriately to the ERA5 0.1° resolution).

Source
------
  WorldPop Global Population Density dataset (2020)
  https://www.worldpop.org/geodata/listing?id=75
  License: Creative Commons Attribution 4.0 International

Output
------
  data/raw/worldpop/
    ppp_2020_1km_Aggregated.tif   global 1km population counts
"""

import hashlib
import sys
from pathlib import Path
from urllib.request import urlretrieve

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# WorldPop 2020 global 1km population count mosaic
# Source: https://www.worldpop.org/geodata/listing?id=75
WORLDPOP_URL = (
    "https://data.worldpop.org/GIS/Population/Global_2000_2020/"
    "2020/0_Mosaicked/ppp_2020_1km_Aggregated.tif"
)

OUTPUT_DIR = Path("data/raw/worldpop")
OUTPUT_FILE = OUTPUT_DIR / "ppp_2020_1km_Aggregated.tif"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def progress_hook(block_num: int, block_size: int, total_size: int) -> None:
    downloaded = block_num * block_size
    if total_size > 0:
        pct = min(100.0, downloaded / total_size * 100)
        mb = downloaded / 1_048_576
        total_mb = total_size / 1_048_576
        print(f"\r  {pct:5.1f}%  {mb:.0f} / {total_mb:.0f} MB", end="", flush=True)


def file_is_valid_geotiff(path: Path) -> bool:
    """Return True if file exists, is non-empty, and opens as a GeoTIFF."""
    if not path.exists() or path.stat().st_size < 1_000_000:
        return False
    try:
        import rasterio

        with rasterio.open(path):
            pass
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Nice Weather — WorldPop Population Download")
    print(f"Source: {WORLDPOP_URL}")
    print(f"Output: {OUTPUT_FILE}")
    print()

    if file_is_valid_geotiff(OUTPUT_FILE):
        size_mb = OUTPUT_FILE.stat().st_size / 1_048_576
        print(f"[SKIP] {OUTPUT_FILE.name} already exists ({size_mb:.0f} MB). "
              "Delete the file and re-run to force a fresh download.")
        return

    print("Downloading … (this may take several minutes for a ~200 MB file)")
    try:
        urlretrieve(WORLDPOP_URL, OUTPUT_FILE, reporthook=progress_hook)
        print()  # newline after progress bar
    except Exception as exc:
        print(f"\n[ERROR] Download failed: {exc}", file=sys.stderr)
        if OUTPUT_FILE.exists():
            OUTPUT_FILE.unlink()
        sys.exit(1)

    if not file_is_valid_geotiff(OUTPUT_FILE):
        print("[ERROR] Downloaded file does not appear to be a valid GeoTIFF.",
              file=sys.stderr)
        OUTPUT_FILE.unlink()
        sys.exit(1)

    size_mb = OUTPUT_FILE.stat().st_size / 1_048_576
    print(f"[OK] {OUTPUT_FILE.name}  ({size_mb:.0f} MB)")


if __name__ == "__main__":
    main()
