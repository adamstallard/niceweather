#!/usr/bin/env python3
"""
bundle_web_data.py

Bundles the binary climate data and GeoJSON boundaries into a single web/data.js
for fully offline (file://) operation. No fetch() calls needed.

Emits:
  - window.PERFECT_WEATHER_DATA = base64-encoded binary
  - window.NE_COUNTRIES = GeoJSON feature collection (countries)
  - window.NE_STATES = GeoJSON feature collection (state/province lines)
"""

import json
import base64
from pathlib import Path

# Map is cropped to this latitude band; clip boundaries to match
# (drops Antarctica entirely, shrinks the bundle)
LAT_CLIP_MIN, LAT_CLIP_MAX = -56.0, 71.0


def clip_ring(ring, lo, hi):
    """Sutherland-Hodgman clip of a polygon ring against lat >= lo and lat <= hi."""
    pts = ring[:-1] if ring[0] == ring[-1] else list(ring)
    for latv, keep in ((lo, lambda p: p[1] >= lo), (hi, lambda p: p[1] <= hi)):
        out = []
        n = len(pts)
        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            a_in, b_in = keep(a), keep(b)
            if a_in != b_in:
                t = (latv - a[1]) / (b[1] - a[1])
                cross = [a[0] + t * (b[0] - a[0]), latv]
            if a_in:
                out.append(a)
                if not b_in:
                    out.append(cross)
            elif b_in:
                out.append(cross)
        pts = out
        if len(pts) < 3:
            return None
    return pts + [pts[0]]


def clip_line(coords, lo, hi):
    """Clip a linestring to the latitude band; returns a list of line parts."""
    def inside(p):
        return lo <= p[1] <= hi

    def crossings(a, b):
        pts = []
        for latv in (lo, hi):
            if (a[1] - latv) * (b[1] - latv) < 0:
                t = (latv - a[1]) / (b[1] - a[1])
                pts.append((t, [a[0] + t * (b[0] - a[0]), latv]))
        return [p for _, p in sorted(pts)]

    parts, cur = [], []
    for i in range(len(coords) - 1):
        a, b = coords[i], coords[i + 1]
        cross = crossings(a, b)
        if inside(a):
            if not cur:
                cur.append(a)
            if inside(b):
                cur.append(b)
            else:
                cur.append(cross[0])
                parts.append(cur)
                cur = []
        elif inside(b):
            cur = [cross[-1], b]
        elif len(cross) == 2:  # segment crosses the entire band
            parts.append(cross)
    if cur:
        parts.append(cur)
    return [p for p in parts if len(p) >= 2]


def clip_geometry(geom):
    """Clip a GeoJSON geometry to the latitude band. Returns None if empty."""
    lo, hi = LAT_CLIP_MIN, LAT_CLIP_MAX
    gtype, coords = geom["type"], geom["coordinates"]

    if gtype == "Polygon":
        ext = clip_ring(coords[0], lo, hi)
        if not ext:
            return None
        rings = [ext] + [r for r in (clip_ring(h, lo, hi) for h in coords[1:]) if r]
        return {"type": "Polygon", "coordinates": rings}

    if gtype == "MultiPolygon":
        polys = []
        for poly in coords:
            clipped = clip_geometry({"type": "Polygon", "coordinates": poly})
            if clipped:
                polys.append(clipped["coordinates"])
        return {"type": "MultiPolygon", "coordinates": polys} if polys else None

    if gtype == "LineString":
        parts = clip_line(coords, lo, hi)
        if not parts:
            return None
        if len(parts) == 1:
            return {"type": "LineString", "coordinates": parts[0]}
        return {"type": "MultiLineString", "coordinates": parts}

    if gtype == "MultiLineString":
        parts = []
        for line in coords:
            parts.extend(clip_line(line, lo, hi))
        return {"type": "MultiLineString", "coordinates": parts} if parts else None

    return geom


def clip_collection(collection, name):
    """Clip all features in a FeatureCollection; drop features left empty."""
    kept = []
    for feat in collection["features"]:
        geom = clip_geometry(feat["geometry"]) if feat.get("geometry") else None
        if geom:
            kept.append({**feat, "geometry": geom})
    print(f"Clipped {name}: {len(collection['features'])} → {len(kept)} features "
          f"(lat {LAT_CLIP_MIN} to {LAT_CLIP_MAX})")
    return {"type": "FeatureCollection", "features": kept}


def main():
    web_dir = Path("web")
    output_file = web_dir / "data.js"

    # 1. Load and encode binary data
    bin_file = Path("data/processed/perfect_weather.bin")
    if not bin_file.exists():
        print(f"Error: {bin_file} not found. Run generate_synthetic_bin.py first.")
        return

    bin_data = bin_file.read_bytes()
    b64_data = base64.b64encode(bin_data).decode("ascii")
    print(f"Encoded {bin_file}: {len(bin_data)} bytes → {len(b64_data)} chars (base64)")

    # 2. Load GeoJSON files
    countries_file = web_dir / "data" / "countries.geojson"
    states_file = web_dir / "data" / "states.geojson"

    countries = clip_collection(json.loads(countries_file.read_text()), "countries")
    states = clip_collection(json.loads(states_file.read_text()), "states")

    # 3. Write bundled data.js
    js_code = f"""// Generated by bundle_web_data.py — do not edit
// Self-contained offline data for Nice Weather

window.PERFECT_WEATHER_DATA = '{b64_data}';

window.NE_COUNTRIES = {json.dumps(countries, separators=(',', ':'))};

window.NE_STATES = {json.dumps(states, separators=(',', ':'))};
"""

    output_file.write_text(js_code)
    size_mb = output_file.stat().st_size / 1_048_576
    print(f"✓ Wrote {output_file} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
