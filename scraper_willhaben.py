"""
Scraper for willhaben.at

NOTE: willhaben.at is heavily JavaScript-rendered. The HTML returned by a plain
requests call does not contain listing cards — the actual content is injected by
React at runtime.  This scraper attempts two strategies:

  1. Parse the __NEXT_DATA__ JSON blob that Next.js embeds in the page
     (this often contains the pre-rendered search results).
  2. Fall back to BeautifulSoup HTML parsing of whatever static markup exists.

If neither strategy yields results, consider switching to Playwright for
full JS rendering.  A comment below marks where to add that integration.
"""

import sys
import json
import re
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup
from config import HEADERS

BASE_URL = "https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz"


def _parse_next_data(soup: BeautifulSoup) -> list[dict]:
    """Extract listings from the __NEXT_DATA__ JSON blob embedded by Next.js."""
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag or not tag.string:
        return []
    try:
        data = json.loads(tag.string)
    except json.JSONDecodeError:
        return []

    # Navigate the Next.js page props — structure may change with site updates
    try:
        props = data["props"]["pageProps"]
        # willhaben embeds search results under various keys; try common paths
        advertiser_list = (
            props.get("searchResult", {}).get("advertSummaryList", {})
            .get("advertSummary", [])
        )
        if not advertiser_list:
            # alternative key seen on some versions
            advertiser_list = (
                props.get("initialState", {})
                .get("searchResult", {})
                .get("advertSummaryList", {})
                .get("advertSummary", [])
            )
    except (KeyError, AttributeError):
        return []

    results = []
    for ad in advertiser_list:
        try:
            attributes = {
                a["name"]: a.get("values", [None])[0]
                for a in ad.get("attributes", {}).get("attribute", [])
            }
            title = ad.get("description") or attributes.get("HEADING", "")
            price_raw = attributes.get("PRICE_FOR_DISPLAY") or attributes.get("PRICE", "")

            # Prefer the SEO-friendly URL from contextLinkList
            url = ""
            ctx_links = ad.get("contextLinkList", {}).get("contextLink", [])
            for link in ctx_links:
                if link.get("id") == "seoSelfLink":
                    rel = link.get("relativePath", "")
                    # relativePath looks like /atverz/kaufen-und-verkaufen/d/title-12345/
                    # strip leading /atverz if present
                    if rel.startswith("/atverz"):
                        rel = rel[len("/atverz"):]
                    url = f"https://www.willhaben.at/iad{rel}"
                    break
            if not url:
                ad_id = ad.get("id", "")
                url = f"https://www.willhaben.at/iad/{ad_id}" if ad_id else ""

            # Thumbnail image
            images = ad.get("advertImageList", {}).get("advertImage", [])
            image_url = images[0].get("thumbnailImageUrl") if images else None

            if title and url:
                results.append({
                    "title": title.strip(),
                    "price": str(price_raw).strip() if price_raw else None,
                    "url": url,
                    "site": "willhaben",
                    "ends_at": None,
                    "image_url": image_url,
                })
        except Exception:
            continue
    return results


def _parse_html_fallback(soup: BeautifulSoup) -> list[dict]:
    """
    Best-effort HTML parsing fallback.
    willhaben renders very little without JS, but we try common selectors.
    """
    results = []

    # Try data-testid or aria-label patterns that sometimes survive SSR
    cards = (
        soup.select("[data-testid='ad-card']")
        or soup.select("article")
        or soup.select(".sc-bdVTJa")  # class names change often
    )

    for card in cards:
        title_el = (
            card.select_one("[data-testid='ad-title']")
            or card.select_one("h3")
            or card.select_one("h2")
        )
        price_el = (
            card.select_one("[data-testid='ad-price']")
            or card.select_one(".price")
        )
        link_el = card.select_one("a[href]")

        title = title_el.get_text(strip=True) if title_el else None
        price = price_el.get_text(strip=True) if price_el else None
        href = link_el["href"] if link_el else None
        if href and not href.startswith("http"):
            href = "https://www.willhaben.at" + href

        if title and href:
            results.append({
                "title": title,
                "price": price,
                "url": href,
                "site": "willhaben",
                "ends_at": None,
            })
    return results


def search_willhaben(keyword: str) -> list[dict]:
    """
    Search willhaben.at for *keyword*.
    Returns a list of dicts: {title, price, url, site, ends_at}.

    NOTE: If the site's JS rendering changes, results may be empty.
    Consider Playwright (playwright.sync_api) for reliable rendering:

        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.goto(url)
            page.wait_for_selector("[data-testid='ad-card']")
            html = page.content()
            browser.close()
    """
    url = f"{BASE_URL}?keyword={quote_plus(keyword)}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[willhaben] Network error for '{keyword}': {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(resp.text, "lxml")

    results = _parse_next_data(soup)
    if results:
        return results

    results = _parse_html_fallback(soup)
    if not results:
        print(
            f"[willhaben] No results parsed for '{keyword}'. "
            "Site may require Playwright for JS rendering.",
            file=sys.stderr,
        )
    return results
