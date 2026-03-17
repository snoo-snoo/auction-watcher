"""
distance.py — Geocoding + distance calculation from home location.

Uses Nominatim (OpenStreetMap) — no API key required.
Results are cached in the SQLite DB to avoid repeated API calls.
"""

import math
import time
import sqlite3
import requests
from config import DB_PATH

HOME_LAT = 48.6455
HOME_LON = 13.9680
HOME_LABEL = "Aigen-Schlägl"

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_HEADERS = {"User-Agent": "auction-watcher/1.0 (github.com/snoo-snoo/auction-watcher)"}
_last_request = 0.0  # rate limit: 1 req/sec


def _init_cache():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS geocache (
                location TEXT PRIMARY KEY,
                lat REAL,
                lon REAL,
                cached_at TEXT
            )
        """)
        conn.commit()


def _geocode(location: str) -> tuple[float, float] | None:
    """Look up coordinates for a location string. Cached in SQLite."""
    global _last_request
    _init_cache()

    location = location.strip()
    if not location:
        return None

    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT lat, lon FROM geocache WHERE location = ?", (location,)
        ).fetchone()
        if row:
            return row[0], row[1]

    # Rate limit: 1 req/sec (Nominatim policy)
    elapsed = time.time() - _last_request
    if elapsed < 1.0:
        time.sleep(1.0 - elapsed)
    _last_request = time.time()

    # Simplify "Wien, XX. Bezirk, Stadtteil" → "Wien"
    import re as _re
    query_location = _re.sub(r",\s*\d+\.\s*Bezirk.*", "", location).strip()
    if not query_location:
        query_location = location

    try:
        r = requests.get(
            _NOMINATIM_URL,
            params={"q": f"{query_location}, Austria", "format": "json", "limit": 1},
            headers=_HEADERS,
            timeout=10,
        )
        results = r.json()
        if not results:
            return None
        lat = float(results[0]["lat"])
        lon = float(results[0]["lon"])
    except Exception:
        return None

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO geocache (location, lat, lon, cached_at) VALUES (?, ?, ?, datetime('now'))",
            (location, lat, lon),
        )
        conn.commit()

    return lat, lon


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km."""
    R = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(d_lon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(a))


def distance_km(location: str) -> float | None:
    """
    Return distance in km from home (Aigen-Schlägl) to *location*.
    Returns None if geocoding fails.
    """
    coords = _geocode(location)
    if coords is None:
        return None
    return round(_haversine(HOME_LAT, HOME_LON, coords[0], coords[1]), 1)


def distance_label(location: str) -> str | None:
    """Return a human-readable distance string, e.g. '28 km'."""
    km = distance_km(location)
    if km is None:
        return None
    return f"{km:.0f} km"
