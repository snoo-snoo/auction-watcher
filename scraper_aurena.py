"""
Scraper for aurena.at (auction platform).

Uses the official lot search API (package 2485524364):
  POST /api/v1/package/2485524364
  { offset, limit, languageCode, filter, query }

Returns individual /posten/ lot URLs with current bid + real total price.
"""

import sys
import re
import requests
from datetime import datetime, timezone
from aurena_auth import get_api_headers, AURENA_API

BASE_URL = "https://www.aurena.at"
SEARCH_PKG = 2485524364
PAGE_SIZE = 96

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


def _parse_ending_date(ms) -> str | None:
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
    except Exception:
        return None


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).strip()


def _lot_to_result(lot: dict) -> dict:
    ld = lot.get("ld", {})
    title = next(iter(ld.get("ti", {}).values()), "")
    desc = _strip_html(next(iter(ld.get("de", {}).values()), ""))

    lot_id = lot.get("lid")
    sp = lot.get("sp") or 0
    hib_val = (lot.get("hib") or {}).get("val") or sp
    if hib_val:
        total = round(hib_val * 1.20 * 1.18, 2)
        label = "Aktuelles Gebot" if (lot.get("hib") or {}).get("val") else "Startpreis"
        price = f"€ {hib_val} ({label}) → ca. € {total:.0f} inkl. MwSt+Provision"
    else:
        price = None

    imgs = lot.get("im", [])
    image_url = imgs[0] if imgs and isinstance(imgs[0], str) else None
    slug = _aurena_slug(title)

    return {
        "title": title,
        "description": desc,
        "price": price,
        "url": f"{BASE_URL}/posten/{lot_id}/{slug}" if lot_id else BASE_URL,
        "site": "aurena",
        "ends_at": _parse_ending_date(lot.get("et")),
        "image_url": image_url,
        "location": None,  # not available at lot level without auction detail
    }


def search_aurena(keyword: str) -> list[dict]:
    """
    Search aurena.at for *keyword* via the official lot search API.
    Returns matching lots with individual /posten/ URLs and real prices.
    """
    headers = get_api_headers()
    results = []
    offset = 0

    while True:
        try:
            r = requests.post(
                f"{AURENA_API}/package/{SEARCH_PKG}",
                json={
                    "offset": offset,
                    "limit": PAGE_SIZE,
                    "languageCode": "de_DE",
                    "filter": {
                        "auctions": [],
                        "bidCount": None,
                        "brands": [],
                        "categories": [],
                        "provinces": [],
                    },
                    "query": keyword,
                },
                headers=headers,
                timeout=15,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"[aurena] Search error: {e}", file=sys.stderr)
            break

        items = data.get("items", [])
        total = data.get("elementCount", 0)

        for lot in items:
            results.append(_lot_to_result(lot))

        offset += len(items)
        if offset >= total or not items:
            break

    if results:
        print(f"[aurena] Found {len(results)} lot(s) for '{keyword}'.", file=sys.stderr)
    else:
        print(f"[aurena] No lots found for '{keyword}'.", file=sys.stderr)

    return results
