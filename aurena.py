import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from config import HEADERS


SEARCH_URL = "https://www.aurena.at/search"
BASE_URL = "https://www.aurena.at"


def _parse_auction_end(text: str) -> str | None:
    """Try to extract ISO datetime from various date string formats."""
    if not text:
        return None
    # Common patterns: "17.03.2026 14:00", "2026-03-17T14:00:00"
    text = text.strip()
    for fmt in ("%d.%m.%Y %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    # Try extracting with regex
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})\s+(\d{2}):(\d{2})", text)
    if m:
        day, month, year, hour, minute = m.groups()
        try:
            return datetime(int(year), int(month), int(day), int(hour), int(minute)).isoformat()
        except ValueError:
            pass
    return None


def search(query: str) -> list[dict]:
    """Search aurena.at and return list of auction listings."""
    results = []
    try:
        resp = requests.get(
            SEARCH_URL,
            params={"q": query},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[aurena] Request error: {e}")
        return results

    try:
        soup = BeautifulSoup(resp.text, "lxml")

        # Aurena uses Bootstrap-style cards or product listing divs.
        cards = (
            soup.select("div.auction-item")
            or soup.select("div.product-item")
            or soup.select("article.lot-card")
            or soup.select("[class*='lot-card']")
            or soup.select("[class*='auction-item']")
            or soup.select("div.card")
        )

        for card in cards[:20]:
            title_el = (
                card.select_one("h2")
                or card.select_one("h3")
                or card.select_one("[class*='title']")
                or card.select_one("[class*='name']")
            )
            price_el = (
                card.select_one("[class*='bid']")
                or card.select_one("[class*='price']")
                or card.select_one("[class*='current']")
            )
            end_el = (
                card.select_one("[class*='end']")
                or card.select_one("[class*='time']")
                or card.select_one("[data-end]")
                or card.select_one("time")
            )
            link_el = card.select_one("a[href]")

            title = title_el.get_text(strip=True) if title_el else "N/A"
            price = price_el.get_text(strip=True) if price_el else "N/A"
            href = link_el["href"] if link_el else None

            if not href or not title or title == "N/A":
                continue

            # Try data-end attribute first, then text
            raw_end = None
            if end_el:
                raw_end = end_el.get("data-end") or end_el.get("datetime") or end_el.get_text(strip=True)
            auction_end = _parse_auction_end(raw_end)

            url = href if href.startswith("http") else f"{BASE_URL}{href}"
            results.append({
                "site": "aurena",
                "title": title,
                "price": price,
                "url": url,
                "auction_end": auction_end,
            })

    except Exception as e:
        print(f"[aurena] Parse error: {e}")

    return results
