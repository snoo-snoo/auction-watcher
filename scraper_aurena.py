"""
Scraper for aurena.at (auction platform).

Strategy:
- Lot IDs on aurena are globally sequential (e.g. lot 4302118 = auction 17515, seq 1)
- We know one anchor: auction 17515 starts at lid 4302118
- For each candidate auction, we estimate its lot ID range by counting
  cumulative lots across earlier auctions, then probe in steps of 200
  until we find the auction's lots
- Matching lots are returned with individual /posten/ URLs

This yields individual product URLs, not auction-level links.
"""

import sys
import re
import time
import sqlite3
import requests
from datetime import datetime, timezone
from aurena_auth import fetch_all_auctions, get_api_headers, AURENA_API
from config import DB_PATH

BASE_URL = "https://www.aurena.at"
LOT_FETCH_PKG = 762574881   # package ID for lot batch fetch (max 96 IDs)
LOT_BATCH_SIZE = 96

_UMLAUT_MAP = str.maketrans({'ä': 'a', 'ö': 'o', 'ü': 'u', 'Ä': 'A', 'Ö': 'O', 'Ü': 'U', 'ß': 'ss'})


def _aurena_slug(title: str) -> str:
    """Convert a lot title to aurena's URL slug format."""
    result = []
    for ch in title.translate(_UMLAUT_MAP):
        if ch == ' ':
            result.append('_0')
        elif ch.isalnum() or ch == '-':
            result.append(ch)
        else:
            result.append(f'_{ord(ch):X}')
    return ''.join(result)

# Anchor: known lot ID for a known auction (verified empirically)
ANCHOR_AUCTION_ID = 17515
ANCHOR_FIRST_LID  = 4302118

# ---------------------------------------------------------------------------
# Lot ID range estimation
# ---------------------------------------------------------------------------

def _estimate_start_lid(target_aid: int, all_auctions: list[dict]) -> int:
    """
    Estimate the starting lot ID for *target_aid* using cumulative lot counts
    relative to the anchor auction.
    """
    sorted_auctions = sorted(all_auctions, key=lambda a: a["auctionId"])

    # Count lots between anchor and target
    lots_between = 0
    for a in sorted_auctions:
        aid = a["auctionId"]
        if aid == ANCHOR_AUCTION_ID:
            break
        if aid >= target_aid:
            break
        lots_between += a["lotCount"]

    if target_aid <= ANCHOR_AUCTION_ID:
        # Target is before anchor — subtract cumulative lots after target up to anchor
        lots_after_target = sum(
            a["lotCount"] for a in sorted_auctions
            if target_aid <= a["auctionId"] < ANCHOR_AUCTION_ID
        )
        return max(ANCHOR_FIRST_LID - lots_after_target - 200, 4000000)
    else:
        # Target is after anchor — add cumulative lots from anchor to target
        lots_after_anchor = sum(
            a["lotCount"] for a in sorted_auctions
            if ANCHOR_AUCTION_ID <= a["auctionId"] < target_aid
        )
        return ANCHOR_FIRST_LID + lots_after_anchor


def _find_start_lid_cached(auction_id: int, all_auctions: list[dict], headers: dict) -> int | None:
    """
    Find the actual first lot ID for *auction_id*.
    Checks a local cache in SQLite first, then probes the API.
    """
    # Cache in SQLite
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS aurena_lot_anchors (
                    auction_id INTEGER PRIMARY KEY,
                    first_lid INTEGER NOT NULL,
                    cached_at TEXT NOT NULL
                )
            """)
            row = conn.execute(
                "SELECT first_lid FROM aurena_lot_anchors WHERE auction_id = ?",
                (auction_id,)
            ).fetchone()
            if row:
                return row[0]
    except Exception:
        pass

    estimate = _estimate_start_lid(auction_id, all_auctions)

    # Probe in steps of 200 until we find this auction's lots
    for offset in range(-400, 1200, 200):
        probe_start = estimate + offset
        batch = list(range(probe_start, probe_start + 200))
        try:
            r = requests.post(
                f"{AURENA_API}/package/{LOT_FETCH_PKG}",
                json={"ids": batch},
                headers=headers,
                timeout=15,
            )
            items = [i for i in r.json().get("items", []) if i.get("aid") == auction_id]
            if items:
                seq1_items = [i for i in items if i["seq"] == 1]
                first_lid = seq1_items[0]["lid"] if seq1_items else min(i["lid"] for i in items)
                # Cache it
                try:
                    with sqlite3.connect(DB_PATH) as conn:
                        conn.execute(
                            "INSERT OR REPLACE INTO aurena_lot_anchors VALUES (?, ?, datetime('now'))",
                            (auction_id, first_lid)
                        )
                        conn.commit()
                except Exception:
                    pass
                return first_lid
        except Exception as e:
            print(f"[aurena] Probe error for auction {auction_id}: {e}", file=sys.stderr)
        time.sleep(0.05)

    return None


# ---------------------------------------------------------------------------
# Lot fetching & filtering
# ---------------------------------------------------------------------------

def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


def _parse_ending_date(ms) -> str | None:
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None


def _fetch_matching_lots(auction: dict, keyword: str, headers: dict, all_auctions: list[dict] = None) -> list[dict]:
    """Fetch all lots for an auction and return those matching keyword."""
    auction_id = auction.get("auctionId")
    lot_count = auction.get("lotCount", 0)
    if not auction_id or lot_count == 0:
        return []

    first_lid = _find_start_lid_cached(auction_id, all_auctions or [auction], headers)
    if first_lid is None:
        return []

    location = auction.get("location", {})
    location_str = ", ".join(filter(None, [location.get("city", ""), location.get("state", "")])) or None
    images = auction.get("images", [])
    auction_image = images[0] if images and isinstance(images[0], str) else None
    ends_at = _parse_ending_date(auction.get("timeInfo", {}).get("endingDate"))
    keyword_lower = keyword.lower()
    results = []

    for offset in range(0, lot_count + LOT_BATCH_SIZE, LOT_BATCH_SIZE):
        batch = list(range(first_lid + offset, first_lid + offset + LOT_BATCH_SIZE))
        try:
            r = requests.post(
                f"{AURENA_API}/package/{LOT_FETCH_PKG}",
                json={"ids": batch},
                headers=headers,
                timeout=15,
            )
            lots = [l for l in r.json().get("items", []) if l.get("aid") == auction_id]
        except Exception as e:
            print(f"[aurena] Lot fetch error auction {auction_id}: {e}", file=sys.stderr)
            break

        if not lots:
            break  # past the end of this auction's lots

        for lot in lots:
            ld = lot.get("ld", {})
            title = next(iter(ld.get("ti", {}).values()), "")
            desc = _strip_html(next(iter(ld.get("de", {}).values()), ""))

            if keyword_lower not in (title + " " + desc).lower():
                continue

            lot_id = lot.get("lid")
            sp = lot.get("sp") or 0
            hib_val = (lot.get("hib") or {}).get("val") or sp
            if hib_val:
                total = round(hib_val * 1.20 * 1.18, 2)
                label = "Aktuelles Gebot" if (lot.get("hib") or {}).get("val") else "Startpreis"
                price = f"€ {hib_val} ({label}) → ca. € {total:.0f} inkl. MwSt+Provision"
            else:
                price = None

            lot_imgs = lot.get("im", [])
            lot_image = lot_imgs[0] if lot_imgs and isinstance(lot_imgs[0], str) else None
            slug = _aurena_slug(title)

            results.append({
                "title": title,
                "description": desc,
                "price": price,
                "url": f"{BASE_URL}/posten/{lot_id}/{slug}" if lot_id else BASE_URL,
                "site": "aurena",
                "ends_at": _parse_ending_date(lot.get("et")) or ends_at,
                "location": location_str,
                "image_url": lot_image or auction_image,
            })

        time.sleep(0.05)

    return results


# ---------------------------------------------------------------------------
# Public search function
# ---------------------------------------------------------------------------

def search_aurena(keyword: str) -> list[dict]:
    """
    Search aurena.at for *keyword* across individual lots.
    Returns matching lots with direct /posten/ URLs.
    """
    all_auctions = fetch_all_auctions()
    if not all_auctions:
        print("[aurena] Could not fetch auctions.", file=sys.stderr)
        return []

    keyword_lower = keyword.lower()

    # Category keyword maps: narrow the auction scope based on search term
    category_hints = {
        "fahrzeug": ["fahrzeug", "kfz", "pkw", "lkw", "van", "kastenwagen", "nutzfahrzeug", "fuhrpark"],
        "transporter": ["fahrzeug", "kfz", "kastenwagen", "van", "nutzfahrzeug", "fuhrpark", "transporter"],
        "vw": ["fahrzeug", "kfz", "pkw", "van", "fuhrpark"],
        "auto": ["fahrzeug", "kfz", "pkw", "fuhrpark"],
        "lkw": ["lkw", "nutzfahrzeug", "fahrzeug"],
        "möbel": ["möbel", "büro", "einrichtung", "auflösung", "lager"],
        "schreibtisch": ["möbel", "büro", "einrichtung", "auflösung"],
        "fenster": ["bau", "fenster", "holz", "auflösung", "lager", "baustoffe"],
        "holzfenster": ["bau", "fenster", "holz", "auflösung"],
        "werkzeug": ["werkzeug", "maschinen", "industrie", "bau", "lager"],
    }

    # Find most specific hint set for this keyword
    filter_terms = None
    for kw_hint, cats in category_hints.items():
        if kw_hint in keyword_lower:
            filter_terms = cats
            break

    # Fall back to a broad filter
    if filter_terms is None:
        filter_terms = [
            "möbel", "büro", "lager", "auflösung", "werkzeug", "bau",
            "fenster", "holz", "haushalt", "elektro", "maschinen",
            "fahrzeug", "kfz", "auto", "van", "kastenwagen", "sport",
            "garten", "industrie", "textil", "lebensmittel", "sanitär",
        ]

    candidates = []
    for auction in all_auctions:
        ld = auction.get("langData", {})
        combined = " ".join(
            list(ld.get("titles", {}).values()) +
            list(ld.get("categoryDescriptions", {}).values()) +
            list(ld.get("shortDescriptions", {}).values())
        ).lower()
        if keyword_lower in combined or any(t in combined for t in filter_terms):
            candidates.append(auction)

    print(f"[aurena] Scanning {len(candidates)}/{len(all_auctions)} auctions for '{keyword}'...", file=sys.stderr)

    headers = get_api_headers()
    # Pre-fetch to enable accurate lid estimation for all auctions
    results = []
    for auction in candidates:
        lots = _fetch_matching_lots(auction, keyword, headers, all_auctions)
        results.extend(lots)

    if results:
        print(f"[aurena] Found {len(results)} lot(s) matching '{keyword}'.", file=sys.stderr)
    else:
        print(f"[aurena] No lots matching '{keyword}' found.", file=sys.stderr)

    return results
