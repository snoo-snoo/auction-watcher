"""
Scraper for aurena.at (auction platform).

Parses search results and extracts auction end times when available.
End times on aurena appear in various formats:
  - "17. März 2026, 14:30 Uhr"
  - ISO-like strings embedded in data attributes
  - Relative strings ("endet in 2 Stunden") — handled as best-effort
"""

import sys
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from config import HEADERS

BASE_URL = "https://www.aurena.at/de/suche"

# German month names → month numbers
DE_MONTHS = {
    "januar": 1, "jänner": 1, "februar": 2, "märz": 3, "april": 4,
    "mai": 5, "juni": 6, "juli": 7, "august": 8, "september": 9,
    "oktober": 10, "november": 11, "dezember": 12,
}


def _parse_german_date(text: str) -> datetime | None:
    """
    Parse German date strings like:
      "17. März 2026, 14:30 Uhr"
      "17.03.2026 14:30"
    Returns UTC datetime or None.
    """
    text = text.strip()

    # Try ISO format first
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    # "17. März 2026, 14:30 Uhr" or "17. März 2026 14:30"
    m = re.search(
        r"(\d{1,2})\.\s*([A-Za-zÄäÖöÜüß]+)\s+(\d{4})[,\s]+(\d{1,2}):(\d{2})",
        text, re.IGNORECASE
    )
    if m:
        day, month_str, year, hour, minute = m.groups()
        month = DE_MONTHS.get(month_str.lower())
        if month:
            try:
                return datetime(int(year), month, int(day), int(hour), int(minute),
                                tzinfo=timezone.utc)
            except ValueError:
                pass

    # "17.03.2026 14:30"
    m = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4})\s+(\d{1,2}):(\d{2})", text)
    if m:
        day, month, year, hour, minute = m.groups()
        try:
            return datetime(int(year), int(month), int(day), int(hour), int(minute),
                            tzinfo=timezone.utc)
        except ValueError:
            pass

    return None


def _parse_relative_date(text: str) -> datetime | None:
    """
    Parse relative strings like "endet in 2 Stunden", "endet in 30 Minuten".
    Returns an approximate UTC datetime.
    """
    now = datetime.now(timezone.utc)
    text_lower = text.lower()

    m = re.search(r"(\d+)\s*stunde", text_lower)
    if m:
        return now + timedelta(hours=int(m.group(1)))

    m = re.search(r"(\d+)\s*minute", text_lower)
    if m:
        return now + timedelta(minutes=int(m.group(1)))

    m = re.search(r"(\d+)\s*tag", text_lower)
    if m:
        return now + timedelta(days=int(m.group(1)))

    return None


def _extract_ends_at(card) -> str | None:
    """
    Try to find an auction end time inside a listing card element.
    Returns ISO string or None.
    """
    # 1. data-ends-at / data-end-time / datetime attributes
    for attr in ("data-ends-at", "data-end-time", "data-auction-end", "datetime"):
        val = card.get(attr)
        if val:
            dt = _parse_german_date(val)
            if dt:
                return dt.isoformat()

    # 2. Any child element with those attributes
    for attr in ("data-ends-at", "data-end-time", "data-auction-end"):
        el = card.find(attrs={attr: True})
        if el:
            dt = _parse_german_date(el[attr])
            if dt:
                return dt.isoformat()

    # 3. Text containing "endet" / "Restzeit" / "Ende"
    for el in card.find_all(string=re.compile(r"endet|restzeit|ende|uhr", re.IGNORECASE)):
        parent_text = el.strip()
        dt = _parse_german_date(parent_text) or _parse_relative_date(parent_text)
        if dt:
            return dt.isoformat()

    return None


def search_aurena(keyword: str) -> list[dict]:
    """
    Search aurena.at for *keyword*.
    Returns a list of dicts: {title, price, url, site, ends_at}.
    ends_at is an ISO UTC string when available, else None.
    """
    url = f"{BASE_URL}?q={quote_plus(keyword)}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[aurena] Network error for '{keyword}': {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(resp.text, "lxml")

    # aurena uses a card-based layout; try multiple selector strategies
    cards = (
        soup.select(".auction-item")
        or soup.select(".lot-item")
        or soup.select("[class*='auction']")
        or soup.select("[class*='lot']")
        or soup.select("article")
        or soup.select(".card")
    )

    results = []
    for card in cards:
        # Title
        title_el = (
            card.select_one("h2")
            or card.select_one("h3")
            or card.select_one(".title")
            or card.select_one("[class*='title']")
        )
        # Price / current bid
        price_el = (
            card.select_one(".price")
            or card.select_one("[class*='price']")
            or card.select_one("[class*='bid']")
            or card.select_one("[class*='gebot']")
        )
        # Link
        link_el = card.select_one("a[href]")

        title = title_el.get_text(strip=True) if title_el else None
        price = price_el.get_text(strip=True) if price_el else None
        href = link_el["href"] if link_el else None
        if href and not href.startswith("http"):
            href = "https://www.aurena.at" + href

        ends_at = _extract_ends_at(card)

        if title and href:
            results.append({
                "title": title,
                "price": price,
                "url": href,
                "site": "aurena",
                "ends_at": ends_at,
            })

    if not results:
        print(
            f"[aurena] No results parsed for '{keyword}'. "
            "Selectors may need updating if the site layout changed.",
            file=sys.stderr,
        )
    return results
