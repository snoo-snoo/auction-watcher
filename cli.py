#!/usr/bin/env python3
"""
cli.py — Command-line interface for auction-watcher

Usage:
  python cli.py add "Büroschrank"      # add keyword to watchlist
  python cli.py list                   # show watchlist
  python cli.py remove "Büroschrank"  # remove keyword (by name)
  python cli.py search "Büroschrank"  # one-shot search, print results
  python cli.py watch                  # run watcher once (for cron)
  python cli.py listings               # show all tracked listings
"""

import argparse
import sys

import db
from scraper_willhaben import search_willhaben
from scraper_aurena import search_aurena
from watcher import run as run_watcher
from link_watch import watch_link


def cmd_add(args):
    keyword = args.keyword.strip()
    if not keyword:
        print("Error: keyword cannot be empty", file=sys.stderr)
        sys.exit(1)
    row_id = db.add_keyword(keyword)
    print(f"Added '{keyword}' (id={row_id})")


def cmd_list(args):
    keywords = db.get_all_keywords()
    if not keywords:
        print("Watchlist is empty.")
        return
    print(f"{'ID':<5} {'Keyword':<40} {'Added'}")
    print("-" * 65)
    for kw_id, keyword, added_at in keywords:
        print(f"{kw_id:<5} {keyword:<40} {added_at}")


def cmd_remove(args):
    keyword = args.keyword.strip()
    keywords = db.get_all_keywords()
    match = next((r for r in keywords if r[1].lower() == keyword.lower()), None)
    if not match:
        print(f"Keyword '{keyword}' not found in watchlist.", file=sys.stderr)
        sys.exit(1)
    kw_id, kw_text, _ = match
    db.remove_keyword(kw_id)
    print(f"Removed '{kw_text}' and its listings.")


def cmd_search(args):
    keyword = args.keyword.strip()
    print(f"Searching for '{keyword}' on willhaben.at and aurena.at ...\n")

    results = []
    try:
        wh = search_willhaben(keyword)
        results += wh
        print(f"willhaben.at: {len(wh)} result(s)")
    except Exception as e:
        print(f"willhaben error: {e}", file=sys.stderr)

    try:
        au = search_aurena(keyword)
        results += au
        print(f"aurena.at:    {len(au)} result(s)")
    except Exception as e:
        print(f"aurena error: {e}", file=sys.stderr)

    if not results:
        print("No results found.")
        return

    print()
    for i, item in enumerate(results, 1):
        title = item.get("title", "–")
        price = item.get("price") or "–"
        url   = item.get("url", "")
        site  = item.get("site", "")
        ends  = item.get("ends_at") or ""
        ends_str = f"  [endet: {ends}]" if ends else ""
        print(f"{i:>3}. [{site}] {title}")
        print(f"     {price}{ends_str}")
        print(f"     {url}")
        print()


def cmd_watch(args):
    run_watcher()


def cmd_track(args):
    """Fetch a listing by URL, add keyword to watchlist, show similar listings."""
    url = args.url.strip()
    print(f"Fetching listing from: {url}\n")

    result = watch_link(url)

    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    listing = result["listing"]
    keywords = result["keywords"]
    search_term = result["search_term"]
    similar = result["similar"]

    print(f"📌 Listing: {listing['title']}")
    if listing.get("price"):
        print(f"   Preis:    {listing['price']}")
    if listing.get("location"):
        print(f"   Ort:      {listing['location']}")
    print(f"   URL:      {listing['url']}")
    print(f"\n🔑 Erkannte Keywords: {', '.join(keywords)}")

    # Add to watchlist
    if not args.no_watch:
        row_id = db.add_keyword(search_term)
        print(f"✅ '{search_term}' zur Watchlist hinzugefügt (id={row_id})")

    # Show similar listings
    if similar:
        print(f"\n🔍 Ähnliche Angebote ({len(similar)} gefunden):\n")
        for i, item in enumerate(similar[:15], 1):
            price = item.get("price") or "–"
            site = item.get("site", "")
            title = item.get("title", "–")
            url_s = item.get("url", "")
            print(f"  {i:>2}. [{site}] {title}")
            print(f"      {price}")
            print(f"      {url_s}")
            print()
    else:
        print("\nKeine ähnlichen Angebote gefunden.")


def cmd_listings(args):
    keywords = {r[0]: r[1] for r in db.get_all_keywords()}
    if not keywords:
        print("Watchlist is empty.")
        return

    all_listings = []
    for kw_id, keyword in keywords.items():
        rows = db.get_listings_for_keyword(kw_id)
        for row in rows:
            all_listings.append((keyword, row))

    if not all_listings:
        print("No listings tracked yet.")
        return

    print(f"{'#':<4} {'Keyword':<20} {'Site':<12} {'Title':<40} {'Price':<12} {'Ends'}")
    print("-" * 110)
    for i, (keyword, row) in enumerate(all_listings, 1):
        lid, site, title, price, url, auction_end, n24, n1 = row
        t = (title[:37] + "...") if len(title) > 40 else title
        p = (price or "–")[:11]
        e = (auction_end or "–")[:19]
        print(f"{i:<4} {keyword:<20} {site:<12} {t:<40} {p:<12} {e}")


def main():
    db.init_db()

    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="auction-watcher: track willhaben.at and aurena.at listings"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Add a keyword to the watchlist")
    p_add.add_argument("keyword", help="Search keyword (e.g. 'Büroschrank')")
    p_add.set_defaults(func=cmd_add)

    p_list = sub.add_parser("list", help="Show current watchlist")
    p_list.set_defaults(func=cmd_list)

    p_remove = sub.add_parser("remove", help="Remove a keyword from the watchlist")
    p_remove.add_argument("keyword", help="Keyword to remove")
    p_remove.set_defaults(func=cmd_remove)

    p_search = sub.add_parser("search", help="One-shot search and print results")
    p_search.add_argument("keyword", help="Keyword to search for")
    p_search.set_defaults(func=cmd_search)

    p_watch = sub.add_parser("watch", help="Run watcher once (suitable for cron)")
    p_watch.set_defaults(func=cmd_watch)

    p_listings = sub.add_parser("listings", help="Show all tracked listings")
    p_listings.set_defaults(func=cmd_listings)

    p_track = sub.add_parser("track", help="Fetch a listing URL, add to watchlist, find similar")
    p_track.add_argument("url", help="willhaben.at or aurena.at listing URL")
    p_track.add_argument("--no-watch", action="store_true", help="Don't add to watchlist, just compare")
    p_track.set_defaults(func=cmd_track)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
