/**
 * Nice Weather — Interactive map visualization using Leaflet
 * Loads perfect_weather.bin and renders probabilities as heatmap overlay
 */

let binaryData = null;
let grid = null;
let map = null;
let heatmapLayer = null;
let isPlaying = false;
let currentHue = { r: 153, g: 0, b: 255 };  // Purple (default)

const monthDays = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

// Visible latitude band (excludes Antarctica, minimizes Arctic distortion)
const BAND_LAT_MIN = -56, BAND_LAT_MAX = 71;

function mercY(lat) {
    // Mercator projection of latitude (radians of projected y)
    return Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI / 180) / 2));
}

function todayDayOfYear() {
    const now = new Date();
    const start = new Date(now.getFullYear(), 0, 1);
    return Math.min(365, Math.floor((now - start) / 86400000) + 1);
}

function getDayName(dayOfYear) {
    let month = 0, day = dayOfYear;
    for (let m of monthDays) {
        if (day <= m) {
            return new Date(2024, month, day).toLocaleDateString('en-US', {
                month: 'short', day: 'numeric'
            });
        }
        day -= m;
        month++;
    }
    return "Jan 1";
}

function probabilityToOpacity(prob) {
    // Probability (0-100) → opacity
    // < 50%: fully transparent (not shown)
    // 50%: barely visible (0.1) → 100%: mostly opaque (0.8)
    if (prob < 50) return 0;
    return 0.1 + ((prob - 50) / 50) * 0.7;
}

function loadBinaryData() {
    try {
        document.getElementById('loading').classList.remove('hidden');

        if (!window.PERFECT_WEATHER_DATA) {
            throw new Error('Binary data not loaded. Ensure web/data.js is loaded before app.js');
        }

        // Decode base64 to binary
        const binaryStr = atob(window.PERFECT_WEATHER_DATA);
        const bytes = new Uint8Array(binaryStr.length);
        for (let i = 0; i < binaryStr.length; i++) {
            bytes[i] = binaryStr.charCodeAt(i);
        }
        const buffer = bytes.buffer;
        const dataView = new DataView(buffer);
        
        // Parse header (big-endian)
        let offset = 0;
        const nCells = dataView.getUint32(offset, false); offset += 4;
        const nDays = dataView.getUint16(offset, false); offset += 2;
        const nLat = dataView.getUint16(offset, false); offset += 2;
        const nLon = dataView.getUint16(offset, false); offset += 2;
        const latMin = dataView.getFloat32(offset, false); offset += 4;
        const latMax = dataView.getFloat32(offset, false); offset += 4;
        const lonMin = dataView.getFloat32(offset, false); offset += 4;
        const lonMax = dataView.getFloat32(offset, false); offset += 4;
        
        grid = {
            nCells, nDays, nLat, nLon,
            latMin, latMax, lonMin, lonMax,
            cells: new Map()
        };
        
        // Parse per-cell data
        for (let i = 0; i < nCells; i++) {
            const latIdx = dataView.getUint16(offset, false); offset += 2;
            const lonIdx = dataView.getUint16(offset, false); offset += 2;
            
            const probs = new Uint8Array(buffer, offset, nDays);
            offset += nDays;
            
            const key = `${latIdx},${lonIdx}`;
            grid.cells.set(key, new Uint8Array(probs));
        }
        
        console.log(`✓ Loaded: ${nCells} cells, ${nLat}×${nLon} grid`);
        document.getElementById('loading').classList.add('hidden');
        
        renderDay(todayDayOfYear()); // Start at today's date
        
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('loading').textContent = `Error: ${error.message}`;
    }
}

function renderDay(dayOfYear) {
    if (!grid || !map) return;

    // Remove old heatmap
    if (heatmapLayer) map.removeLayer(heatmapLayer);

    // Overlay covers the data grid clipped to the visible latitude band
    const latTop = Math.min(grid.latMax, BAND_LAT_MAX);
    const latBottom = Math.max(grid.latMin, BAND_LAT_MIN);
    const dLat = (grid.latMax - grid.latMin) / grid.nLat;

    // Canvas sized to grid resolution (capped), height proportioned in Mercator space
    // so rows line up exactly with the map underneath
    const canvasWidth = Math.min(grid.nLon * 2, 2880);
    const yTopM = mercY(latTop), yBottomM = mercY(latBottom);
    const lonSpanRad = (grid.lonMax - grid.lonMin) * Math.PI / 180;
    const canvasHeight = Math.round(canvasWidth * (yTopM - yBottomM) / lonSpanRad);
    const canvas = document.createElement('canvas');
    canvas.width = canvasWidth;
    canvas.height = canvasHeight;
    const ctx = canvas.getContext('2d');
    const yScale = canvasHeight / (yTopM - yBottomM);

    for (const [key, probs] of grid.cells) {
        const prob = probs[dayOfYear - 1] || 0;
        const opacity = probabilityToOpacity(prob);
        if (opacity <= 0) continue;  // Below 50%: not shown

        const [latIdx, lonIdx] = key.split(',').map(Number);
        const lat0 = grid.latMin + latIdx * dLat;           // south edge
        const lat1 = lat0 + dLat;                           // north edge
        if (lat1 <= latBottom || lat0 >= latTop) continue;  // outside band

        // Mercator-project cell edges; rounded so adjacent cells tile exactly
        const y0 = Math.round((yTopM - mercY(Math.min(lat1, latTop))) * yScale);
        const y1 = Math.round((yTopM - mercY(Math.max(lat0, latBottom))) * yScale);
        const x0 = Math.round(lonIdx / grid.nLon * canvasWidth);
        const x1 = Math.round((lonIdx + 1) / grid.nLon * canvasWidth);

        ctx.fillStyle = `rgba(${currentHue.r}, ${currentHue.g}, ${currentHue.b}, ${opacity})`;
        ctx.fillRect(x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0));
    }

    // Create image overlay (in dedicated pane above boundaries)
    const imageUrl = canvas.toDataURL();
    heatmapLayer = L.imageOverlay(imageUrl, [
        [latTop, grid.lonMin],
        [latBottom, grid.lonMax]
    ], { opacity: 1.0, pane: 'heatmap' }).addTo(map);

    // Update display
    document.getElementById('dayDisplay').textContent = getDayName(dayOfYear);
    document.getElementById('daySlider').value = dayOfYear;
}

function startPlayback() {
    isPlaying = !isPlaying;
    const btn = document.getElementById('playButton');
    
    if (!isPlaying) {
        btn.classList.remove('playing');
        btn.textContent = '▶ Play';
        return;
    }
    
    btn.classList.add('playing');
    btn.textContent = '⏸ Pause';
    
    let day = parseInt(document.getElementById('daySlider').value);
    const interval = setInterval(() => {
        day = day >= 365 ? 1 : day + 1;
        renderDay(day);
        
        if (!isPlaying) clearInterval(interval);
    }, 150);
}

function loadBoundaries() {
    // Offline political boundaries from window.NE_COUNTRIES and window.NE_STATES
    try {
        if (!window.NE_COUNTRIES || !window.NE_STATES) {
            console.error('Boundary data not loaded. Ensure web/data.js is loaded before app.js');
            return;
        }

        // Country polygons (land fill + borders); non-interactive so map clicks pass through
        L.geoJSON(window.NE_COUNTRIES, {
            interactive: false,
            style: {
                color: '#888',
                weight: 1,
                fillColor: '#d9d0c1',
                fillOpacity: 1
            }
        }).addTo(map);

        // State/province lines
        L.geoJSON(window.NE_STATES, {
            interactive: false,
            style: {
                color: '#aaa',
                weight: 0.5,
                fill: false
            }
        }).addTo(map);
    } catch (error) {
        console.error('Failed to load boundaries:', error);
    }
}

function bestDayOf(probs) {
    let day = 1, prob = -1;
    for (let i = 0; i < probs.length; i++) {
        if (probs[i] > prob) { prob = probs[i]; day = i + 1; }
    }
    return { day, prob };
}

function drawSparkline(canvas, probs, markedDay) {
    const ctx = canvas.getContext('2d');
    const w = canvas.width, h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    // 50% threshold line
    ctx.strokeStyle = '#ddd';
    ctx.beginPath();
    ctx.moveTo(0, h / 2 + 0.5);
    ctx.lineTo(w, h / 2 + 0.5);
    ctx.stroke();

    // Probability curve (current hue)
    ctx.strokeStyle = `rgb(${currentHue.r}, ${currentHue.g}, ${currentHue.b})`;
    ctx.beginPath();
    for (let i = 0; i < probs.length; i++) {
        const x = i / (probs.length - 1) * w;
        const y = h - (probs[i] / 100) * h;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Marker for the selected day
    ctx.strokeStyle = '#999';
    const mx = (markedDay - 1) / (probs.length - 1) * w;
    ctx.beginPath();
    ctx.moveTo(mx, 0);
    ctx.lineTo(mx, h);
    ctx.stroke();
}

function showInspectPopup(latlng) {
    if (!grid) return;
    const lon = ((latlng.lng + 180) % 360 + 360) % 360 - 180;  // wrap to [-180, 180)
    const latIdx = Math.floor((latlng.lat - grid.latMin) / (grid.latMax - grid.latMin) * grid.nLat);
    const lonIdx = Math.floor((lon - grid.lonMin) / (grid.lonMax - grid.lonMin) * grid.nLon);
    const probs = grid.cells.get(`${latIdx},${lonIdx}`);

    const el = document.createElement('div');
    el.className = 'inspect-popup';
    if (!probs) {
        el.textContent = 'No data here — below 50% year-round, or unpopulated.';
    } else {
        const day = parseInt(document.getElementById('daySlider').value);
        const best = bestDayOf(probs);

        const headline = document.createElement('div');
        headline.className = 'inspect-headline';
        headline.textContent = `${probs[day - 1]}% on ${getDayName(day)}`;

        const spark = document.createElement('canvas');
        spark.width = 240;
        spark.height = 48;
        drawSparkline(spark, probs, day);

        const btn = document.createElement('button');
        btn.className = 'inspect-best';
        btn.textContent = `Best day: ${getDayName(best.day)} (${best.prob}%)`;
        btn.addEventListener('click', () => {
            renderDay(best.day);
            headline.textContent = `${best.prob}% on ${getDayName(best.day)}`;
            drawSparkline(spark, probs, best.day);
        });

        el.append(headline, spark, btn);
    }
    L.popup().setLatLng(latlng).setContent(el).openOn(map);
}

// Band aspect ratio in Mercator space (width / height)
const BAND_ASPECT = (2 * Math.PI) / (mercY(BAND_LAT_MAX) - mercY(BAND_LAT_MIN));

function applyDefaultView(maxBounds) {
    // Size the map element to the band's aspect ratio so the full band fits
    // exactly, with any leftover vertical space left as an empty bar below
    // the map (never above, never hidden map). Then reset zoom and pan.
    const mapEl = document.getElementById('map');
    const mainEl = mapEl.parentElement;
    const availW = mainEl.clientWidth;
    const availH = mainEl.clientHeight - document.getElementById('controls').offsetHeight;
    mapEl.style.flex = 'none';
    mapEl.style.height = Math.min(availH, Math.round(availW / BAND_ASPECT)) + 'px';
    map.invalidateSize({ animate: false });

    const z = map.getBoundsZoom(maxBounds);
    map.setMinZoom(z);
    map.setView(maxBounds.getCenter(), z, { animate: false });
}

document.addEventListener('DOMContentLoaded', () => {
    // Initialize Leaflet map (offline: vector boundaries, no tile server)
    // Crop to -56° to +71° latitude (excludes Antarctica, minimizes Arctic distortion)
    const maxBounds = L.latLngBounds([[-56, -180], [71, 180]]);
    map = L.map('map', { maxZoom: 8, maxBounds, maxBoundsViscosity: 1.0, zoomSnap: 0 });

    applyDefaultView(maxBounds);

    // On browser resize, return to the default view at the new viewport size
    window.addEventListener('resize', () => applyDefaultView(maxBounds));

    // Heatmap pane sits above boundary vectors (overlayPane is 400)
    map.createPane('heatmap');
    map.getPane('heatmap').style.zIndex = 450;

    loadBoundaries();

    // Click to inspect a grid cell
    map.on('click', (e) => showInspectPopup(e.latlng));

    // Slider event
    document.getElementById('daySlider').addEventListener('input', (e) => {
        isPlaying = false;
        document.getElementById('playButton').classList.remove('playing');
        document.getElementById('playButton').textContent = '▶ Play';
        renderDay(parseInt(e.target.value));
    });
    
    // Play button
    document.getElementById('playButton').addEventListener('click', startPlayback);

    // Hue picker
    document.querySelectorAll('.hue-swatch').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const hex = e.target.dataset.hue;
            currentHue = {
                r: parseInt(hex.substring(0, 2), 16),
                g: parseInt(hex.substring(2, 4), 16),
                b: parseInt(hex.substring(4, 6), 16)
            };

            // Update selected state
            document.querySelectorAll('.hue-swatch').forEach(s => s.removeAttribute('data-selected'));
            e.target.setAttribute('data-selected', 'true');

            // Update legend bar color
            const legendBar = document.querySelector('.legend-bar');
            legendBar.style.backgroundImage = `linear-gradient(to right, rgba(${currentHue.r}, ${currentHue.g}, ${currentHue.b}, 0.1), rgba(${currentHue.r}, ${currentHue.g}, ${currentHue.b}, 0.8))`;

            // Re-render current day with new hue
            const currentDay = parseInt(document.getElementById('daySlider').value);
            renderDay(currentDay);
        });
    });

    // Load data
    loadBinaryData();
});
