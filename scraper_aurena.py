"""
Scraper for aurena.at (auction platform).

Uses the authenticated REST API (via aurena_auth.py) to fetch all active
auctions and filter by keyword across title, category, and description fields.

NOTE: Aurena auctions are grouped by auction event (e.g. "Büroauflösung Wien"),
not individual lots. The scraper matches against auction-level metadata.
For lot-level search, a full Playwright/browser approach would be needed.
"""

import sys
from datetime import datetime, timezone
from aurena_auth import fetch_all_auctions

BASE_URL = "https://www.aurena.at"


def _parse_ending_date(time_info: dict) -> str | None:
    """Parse endingDate (Unix ms timestamp) to ISO string."""
    ending_ms = time_info.get("endingDate")
    if not ending_ms:
        return None
    try:
        dt = datetime.fromtimestamp(ending_ms / 1000, tz=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError, OSError):
        return None


def _auction_to_result(auction: dict) -> dict:
    """Convert raw auction API dict to scraper result format."""
    lang_data = auction.get("langData", {})
    titles = lang_data.get("titles", {})
    short_descs = lang_data.get("shortDescriptions", {})
    cat_descs = lang_data.get("categoryDescriptions", {})

    # Prefer German title
    title = (
        titles.get("de_DE")
        or titles.get("de_AT")
        or next(iter(titles.values()), "")
    )
    location = auction.get("location", {})
    city = location.get("city", "")
    state = location.get("state", "")
    location_str = ", ".join(filter(None, [city, state])) or None

    auction_id = auction.get("auctionId", "")
    url = f"{BASE_URL}/auktionen/{auction_id}" if auction_id else BASE_URL

    time_info = auction.get("timeInfo", {})
    ends_at = _parse_ending_date(time_info)

    # First image from auction (list of URL strings)
    images = auction.get("images", [])
    image_url = images[0] if images and isinstance(images[0], str) else None

    return {
        "title": title,
        "price": None,
        "url": url,
        "site": "aurena",
        "ends_at": ends_at,
        "location": location_str,
        "image_url": image_url,
        # keep extra fields for keyword matching (not shown in output)
        "_cat": " ".join(cat_descs.values()),
        "_short_desc": " ".join(short_descs.values()),
    }


def search_aurena(keyword: str) -> list[dict]:
    """
    Search aurena.at for *keyword* by fetching all auctions via API and
    filtering by title, category, and short description.
    Returns list of dicts: {title, price, url, site, ends_at}.
    """
    all_auctions = fetch_all_auctions()

    if not all_auctions:
        print("[aurena] Could not fetch auctions.", file=sys.stderr)
        return []

    keyword_lower = keyword.lower()

    # Build list of search terms (keyword + common synonyms)
    terms = [keyword_lower]
    synonyms = {
        "büroschrank": ["schrank", "aktenschrank", "büromöbel"],
        "schreibtisch": ["tisch", "büromöbel"],
        "stuhl": ["sessel", "bürostuhl"],
        "sofa": ["couch", "sitzgarnitur"],
        "kühlschrank": ["kühlgerät"],
        "fenster": ["holzfenster", "kunststofffenster", "fensterrahmen"],
        "holzfenster": ["fenster", "holzfenster"],
    }
    for key, syns in synonyms.items():
        if key in keyword_lower:
            terms.extend(syns)

    results = []
    for auction in all_auctions:
        result = _auction_to_result(auction)
        combined = " ".join([
            result["title"],
            result.get("_cat", ""),
            result.get("_short_desc", ""),
            result.get("location") or "",
        ]).lower()

        if any(term in combined for term in terms):
            # Strip internal fields before returning
            results.append({k: v for k, v in result.items() if not k.startswith("_")})

    if not results:
        print(
            f"[aurena] No auctions matching '{keyword}' found among {len(all_auctions)} listings.",
            file=sys.stderr,
        )

    return results
