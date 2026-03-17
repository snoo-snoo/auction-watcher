"""
Scraper for aurena.at (auction platform).

Aurena is an Angular SPA - the homepage loads all upcoming auctions as Angular components.
We fetch the homepage HTML, parse auction entries, and filter by keyword.

Auction data structure in HTML:
  <auctionentry> elements with:
    - <p class=title innerhtml="..."> for title
    - <div class=num innerhtml="DD"> and <div class=month innerhtml="MMM"> for date
    - <div class=state-text innerhtml="location"> for location
    - Links to /auktionen/{id}/{slug}
"""

import sys
import re
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import requests
from config import HEADERS

BASE_URL = "https://www.aurena.at"
AUCTIONS_URL = "https://www.aurena.at"  # homepage has all upcoming auctions

# German month abbreviations → month numbers
DE_MONTHS_SHORT = {
    "jan": 1, "jän": 1, "feb": 2, "mär": 3, "mar": 3,
    "apr": 4, "mai": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "okt": 10, "nov": 11, "dez": 12,
}

# Full German month names
DE_MONTHS_FULL = {
    "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8, "september": 9,
    "oktober": 10, "november": 11, "dezember": 12,
}


def _parse_auction_date(day_str: str, month_str: str) -> str | None:
    """
    Parse day number and German month abbreviation into ISO date string.
    e.g. day_str="27", month_str="Mär" -> "2026-03-27T00:00:00+00:00"
    """
    try:
        day = int(day_str.strip())
        month_key = month_str.strip().lower()[:3]
        month = DE_MONTHS_SHORT.get(month_key)
        if not month:
            return None
        # Assume current or next year
        now = datetime.now(timezone.utc)
        year = now.year
        # If month is in the past, assume next year
        if month < now.month or (month == now.month and day < now.day):
            year += 1
        dt = datetime(year, month, day, tzinfo=timezone.utc)
        return dt.isoformat()
    except (ValueError, TypeError):
        return None


def _fetch_all_auctions() -> list[dict]:
    """
    Fetch aurena.at homepage and parse all upcoming auction entries.
    Returns list of dicts: {title, url, ends_at, location, site}
    """
    try:
        resp = requests.get(AUCTIONS_URL, headers=HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[aurena] Request error: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    auctions = []

    # Find all <auctionentry> elements
    entries = soup.find_all("auctionentry")
    if not entries:
        # Fallback: find by class pattern
        entries = soup.find_all(class_=re.compile(r"auction"))

    for entry in entries:
        # Title
        title_el = entry.find("p", class_="title")
        if not title_el:
            # Try innerhtml attribute
            title_el = entry.find(attrs={"innerhtml": True})
        title = None
        if title_el:
            # Use innerhtml attribute if present (aurena uses it)
            title = title_el.get("innerhtml") or title_el.get_text(strip=True)

        if not title:
            continue

        # Date: <div class=num innerhtml="DD"> and <div class=month innerhtml="MMM">
        day_el = entry.find(class_="num")
        month_el = entry.find(class_="month")
        ends_at = None
        if day_el and month_el:
            day = day_el.get("innerhtml") or day_el.get_text(strip=True)
            month = month_el.get("innerhtml") or month_el.get_text(strip=True)
            ends_at = _parse_auction_date(day, month)

        # Location
        location_el = entry.find(class_="state-text")
        location = None
        if location_el:
            location = location_el.get("innerhtml") or location_el.get_text(strip=True)

        # URL: find link in parent or nearby
        link_el = entry.find_parent("a") or entry.find("a", href=True)
        url = None
        if link_el and link_el.get("href"):
            href = link_el["href"]
            if not href.startswith("http"):
                href = BASE_URL + href
            url = href
        else:
            # Generate search URL as fallback
            slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
            url = f"{BASE_URL}/auktionen"

        auctions.append({
            "title": title,
            "url": url,
            "ends_at": ends_at,
            "location": location,
            "site": "aurena",
            "price": None,
        })

    return auctions


def search_aurena(keyword: str) -> list[dict]:
    """
    Search aurena.at for *keyword* by fetching all auctions and filtering by title.
    Returns list of dicts: {title, price, url, site, ends_at}.
    """
    all_auctions = _fetch_all_auctions()

    if not all_auctions:
        print(f"[aurena] Could not fetch auctions listing.", file=sys.stderr)
        return []

    # Filter by keyword (case-insensitive, partial match)
    keyword_lower = keyword.lower()
    # Also check related terms
    keywords = [keyword_lower]

    # Add German synonyms for common items
    synonyms = {
        "büroschrank": ["büromöbel", "schrank", "aktenschrank", "regal", "büro"],
        "schreibtisch": ["büromöbel", "tisch", "büro"],
        "stuhl": ["sessel", "bürostuhl", "sitzgelegenheit"],
        "sofa": ["couch", "sitzgarnitur", "möbel"],
        "kühlschrank": ["kühlgerät", "kühlung"],
    }
    for key, syns in synonyms.items():
        if key in keyword_lower:
            keywords.extend(syns)

    results = []
    for auction in all_auctions:
        title_lower = auction["title"].lower()
        location_lower = (auction.get("location") or "").lower()
        combined = title_lower + " " + location_lower

        if any(kw in combined for kw in keywords):
            results.append(auction)

    if not results:
        print(
            f"[aurena] No auctions matching '{keyword}' found among {len(all_auctions)} listings.",
            file=sys.stderr,
        )

    return results
