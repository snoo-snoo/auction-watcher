"""
link_watch.py — Fetch a willhaben or aurena listing by URL,
extract its title/keywords, add to watchlist, and search for similar listings.
"""

import re
import sys
import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse

from config import HEADERS
from scraper_willhaben import search_willhaben
from scraper_aurena import search_aurena


# --- URL detection ---

def detect_site(url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    if "willhaben" in host:
        return "willhaben"
    if "aurena" in host:
        return "aurena"
    return None


# --- Willhaben detail fetch ---

def fetch_willhaben_listing(url: str) -> dict | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[link_watch] Error fetching willhaben URL: {e}", file=sys.stderr)
        return None

    soup = BeautifulSoup(resp.text, "lxml")
    tag = soup.find("script", id="__NEXT_DATA__")
    if not tag:
        return None

    try:
        data = json.loads(tag.string)
        ad = data["props"]["pageProps"]["advertDetails"]
        attrs = {
            a["name"]: a.get("values", [""])[0]
            for a in ad.get("attributes", {}).get("attribute", [])
        }
        title = ad.get("description", "")
        price = attrs.get("PRICE_FOR_DISPLAY") or attrs.get("PRICE")
        location = attrs.get("LOCATION", "")
        return {
            "site": "willhaben",
            "title": title,
            "price": price,
            "url": url,
            "location": location,
        }
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        print(f"[link_watch] Could not parse willhaben listing: {e}", file=sys.stderr)
        return None


# --- Aurena detail fetch ---

def fetch_aurena_listing(url: str) -> dict | None:
    """
    Extract auction ID from aurena URL and fetch details via API.
    URL pattern: https://www.aurena.at/auktionen/{id}/{slug}
    """
    match = re.search(r"/auktionen/(\d+)", url)
    if not match:
        print(f"[link_watch] Could not extract aurena auction ID from URL", file=sys.stderr)
        return None

    from aurena_auth import fetch_all_auctions
    auction_id = int(match.group(1))
    auctions = fetch_all_auctions()
    auction = next((a for a in auctions if a.get("auctionId") == auction_id), None)

    if not auction:
        print(f"[link_watch] Auction {auction_id} not found in active listings", file=sys.stderr)
        return None

    lang_data = auction.get("langData", {})
    titles = lang_data.get("titles", {})
    title = titles.get("de_DE") or next(iter(titles.values()), "")
    location = auction.get("location", {})
    city = location.get("city", "")

    return {
        "site": "aurena",
        "title": title,
        "price": None,
        "url": url,
        "location": city,
    }


# --- Keyword extraction ---

def extract_keywords(title: str) -> list[str]:
    """
    Extract 1-3 meaningful search keywords from a listing title.
    Strips common filler words, returns the most relevant noun phrases.
    """
    stopwords = {
        "und", "oder", "mit", "für", "von", "zu", "an", "auf", "in", "im",
        "aus", "bei", "nach", "über", "vor", "zum", "zur", "am", "als", "wie",
        "der", "die", "das", "den", "dem", "des", "ein", "eine", "einen",
        "stk", "stück", "inkl", "incl", "ca", "neu", "alt", "gebraucht",
        "verschiedene", "verschiedenen", "verfügbar", "abzuholen", "jahre",
    }

    # Split on common separators
    words = re.split(r"[\s,\-/|&()]+", title)
    keywords = []
    for w in words:
        w_clean = w.strip(".")
        if len(w_clean) >= 4 and w_clean.lower() not in stopwords:
            keywords.append(w_clean)

    # Return up to 3 most meaningful words (longer = more specific)
    keywords = sorted(set(keywords), key=len, reverse=True)[:3]
    return keywords


# --- Main entry point ---

def watch_link(url: str) -> dict:
    """
    Given a willhaben or aurena URL:
    1. Fetch the listing details
    2. Extract keywords
    3. Search for similar listings
    Returns dict with listing info and similar results.
    """
    site = detect_site(url)
    if not site:
        return {"error": f"Unsupported URL: {url}"}

    # Fetch listing details
    if site == "willhaben":
        listing = fetch_willhaben_listing(url)
    else:
        listing = fetch_aurena_listing(url)

    if not listing:
        return {"error": f"Could not fetch listing from {url}"}

    title = listing["title"]
    keywords = extract_keywords(title)

    # Use the most specific keyword for the search
    search_term = keywords[0] if keywords else title.split()[0]

    # Also try a combined 2-word search if we have multiple keywords
    search_terms = [search_term]
    if len(keywords) >= 2:
        search_terms.append(f"{keywords[0]} {keywords[1]}")

    # Search for similar listings
    similar = []
    seen_urls = {url}  # exclude the original listing
    for term in search_terms:
        results = search_willhaben(term) + search_aurena(term)
        for r in results:
            if r["url"] not in seen_urls:
                seen_urls.add(r["url"])
                similar.append(r)

    # Sort by price (cheapest first, None last)
    def price_sort_key(r):
        p = r.get("price") or ""
        nums = re.findall(r"[\d.,]+", str(p).replace(".", "").replace(",", "."))
        try:
            return float(nums[0]) if nums else float("inf")
        except ValueError:
            return float("inf")

    similar.sort(key=price_sort_key)

    return {
        "listing": listing,
        "keywords": keywords,
        "search_term": search_term,
        "similar": similar[:20],
    }
