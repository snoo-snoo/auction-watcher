import requests
from bs4 import BeautifulSoup
from config import HEADERS


SEARCH_URL = "https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz"


def search(query: str) -> list[dict]:
    """Search willhaben.at and return list of listings."""
    results = []
    try:
        resp = requests.get(
            SEARCH_URL,
            params={"keyword": query},
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[willhaben] Request error: {e}")
        return results

    try:
        soup = BeautifulSoup(resp.text, "lxml")

        # Willhaben renders listings in article elements or data attributes.
        # Try multiple selector strategies.
        cards = soup.select("article[data-testid='result-item']")
        if not cards:
            cards = soup.select("[data-testid='result-item']")
        if not cards:
            # Fallback: look for common listing containers
            cards = soup.select("div.sc-1x3cxgp-0, div[class*='ResultList']")

        for card in cards[:20]:
            title_el = (
                card.select_one("[data-testid='ad-title']")
                or card.select_one("h2")
                or card.select_one("h3")
            )
            price_el = (
                card.select_one("[data-testid='ad-price']")
                or card.select_one("[class*='price']")
            )
            link_el = card.select_one("a[href]")

            title = title_el.get_text(strip=True) if title_el else "N/A"
            price = price_el.get_text(strip=True) if price_el else "N/A"
            href = link_el["href"] if link_el else None

            if not href or not title or title == "N/A":
                continue

            url = href if href.startswith("http") else f"https://www.willhaben.at{href}"
            results.append({
                "site": "willhaben",
                "title": title,
                "price": price,
                "url": url,
                "auction_end": None,
            })

    except Exception as e:
        print(f"[willhaben] Parse error: {e}")

    return results
