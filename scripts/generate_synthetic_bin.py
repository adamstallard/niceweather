#!/usr/bin/env python3
"""
generate_synthetic_bin.py

Creates a synthetic perfect_weather.bin file for testing the web UI.
Binary format: 26-byte header + per-cell data (4 + 365 bytes per cell).
Then bundles it with GeoJSON boundaries into web/data.js for offline use.
"""

import struct
import subprocess
import sys
import numpy as np
from pathlib import Path

# Grid parameters (subset for faster testing)
LAT_MIN, LAT_MAX = -90.0, 90.0
LON_MIN, LON_MAX = -180.0, 180.0
N_LAT, N_LON = 180, 360  # Coarse grid for testing

OUTPUT_PATH = Path("data/processed/perfect_weather.bin")

def generate_synthetic_bin():
    """Generate synthetic binary data for web app testing."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    np.random.seed(42)
    cells = []
    
    for i_lat in range(N_LAT):
        lat = LAT_MIN + (i_lat / N_LAT) * (LAT_MAX - LAT_MIN)
        
        for i_lon in range(N_LON):
            lon = LON_MIN + (i_lon / N_LON) * (LON_MAX - LON_MIN)
            
            # Higher probability in tropics
            lat_factor = max(0, 1.0 - abs(lat) / 60.0)
            
            # Generate 365 daily probabilities
            probs = np.zeros(365, dtype=np.uint8)
            for day in range(365):
                # Seasonal variation
                if lat > 0:
                    seasonal = np.sin((day - 80) * 2 * np.pi / 365)
                else:
                    seasonal = -np.sin((day - 80) * 2 * np.pi / 365)
                
                noise = np.random.normal(0, 0.1)
                base = 0.3 + lat_factor * 0.4 + seasonal * 0.2 + noise
                prob = int(np.clip(base * 100, 0, 100))
                probs[day] = prob
            
            if probs.max() >= 50:  # Only include cells where max prob >= 50%
                cells.append((i_lat, i_lon, probs))
    
    n_cells = len(cells)
    print(f"Generated {n_cells} populated cells")
    
    # Write binary: 20-byte header + per-cell data
    with open(OUTPUT_PATH, "wb") as f:
        # Header: uint32 + uint16*3 + float32*4 = 26 bytes (not 20 per spec, but works)
        # Format: >I = uint32, >H = uint16, >f = float32 (all big-endian)
        fmt = ">IHHHffff"  # 1 uint32 + 3 uint16 + 4 float32
        header = struct.pack(
            fmt,
            n_cells,   # uint32 (4 bytes)
            365,       # uint16 (2 bytes)
            N_LAT,     # uint16 (2 bytes)
            N_LON,     # uint16 (2 bytes)
            LAT_MIN,   # float32 (4 bytes)
            LAT_MAX,   # float32 (4 bytes)
            LON_MIN,   # float32 (4 bytes)
            LON_MAX    # float32 (4 bytes)
        )
        f.write(header)
        
        # Per-cell data
        for i_lat, i_lon, probs in cells:
            f.write(struct.pack(">HH", i_lat, i_lon))
            f.write(probs.tobytes())
    
    size_mb = OUTPUT_PATH.stat().st_size / 1_048_576
    print(f"✓ Wrote {OUTPUT_PATH} ({size_mb:.2f} MB)")

    # Bundle with GeoJSON into web/data.js for offline use
    try:
        print("\nBundling data into web/data.js...")
        subprocess.run([sys.executable, "scripts/bundle_web_data.py"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Warning: Failed to bundle data: {e}")

if __name__ == "__main__":
    generate_synthetic_bin()
