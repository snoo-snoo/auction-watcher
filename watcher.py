"""
watcher.py — main run loop (intended for cron / `python cli.py watch`)

Steps:
  1. Load all keywords from wishlist_items
  2. Search both sites for each keyword
  3. Upsert listings; collect newly discovered ones
  4. Send Telegram suggestion batches for new listings
  5. Check auction end times on existing listings:
       - Send 24h reminder once
       - Send 1h reminder once
  6. Mark listings whose auction has already ended as inactive
     (sets notified_24h=1, notified_1h=1 so we never re-alert)
"""

import sys
from datetime import datetime, timezone

import db
from scraper_willhaben import search_willhaben
from scraper_aurena import search_aurena
from telegram_bot import send_suggestions, send_listing_alert


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _hours_until(dt: datetime) -> float:
    delta = dt - _now_utc()
    return delta.total_seconds() / 3600


def run():
    db.init_db()
    keywords = db.get_all_keywords()  # list of (id, keyword, added_at)

    if not keywords:
        print("[watcher] Watchlist is empty. Add keywords with: python cli.py add <keyword>")
        return

    for kw_row in keywords:
        kw_id, keyword, _ = kw_row
        print(f"[watcher] Searching for: {keyword}")

        results = []
        try:
            results += search_willhaben(keyword)
        except Exception as e:
            print(f"[watcher] willhaben error: {e}", file=sys.stderr)
        try:
            results += search_aurena(keyword)
        except Exception as e:
            print(f"[watcher] aurena error: {e}", file=sys.stderr)

        new_listings = []
        for item in results:
            is_new, n24, n1 = db.upsert_listing(
                wishlist_id=kw_id,
                site=item.get("site", ""),
                title=item.get("title", ""),
                price=item.get("price"),
                url=item.get("url", ""),
                auction_end=item.get("ends_at"),
                image_url=item.get("image_url"),
            )
            if is_new:
                new_listings.append(item)

        if new_listings:
            print(f"[watcher] {len(new_listings)} new listing(s) for '{keyword}'")
            send_suggestions(keyword, new_listings)
        else:
            print(f"[watcher] No new listings for '{keyword}'")

    # --- Auction reminder pass ---
    for kw_row in keywords:
        kw_id, keyword, _ = kw_row
        listings = db.get_listings_for_keyword(kw_id)
        # columns: id, site, title, price, url, auction_end, notified_24h, notified_1h

        for row in listings:
            lid, site, title, price, url, auction_end, n24, n1 = row
            ends_dt = _parse_iso(auction_end)
            if not ends_dt:
                continue

            hours_left = _hours_until(ends_dt)

            if hours_left < 0:
                # Auction over — mark as fully notified to prevent future alerts
                if not (n24 and n1):
                    db.set_notified(lid, flag_24h=True, flag_1h=True)
                continue

            listing_dict = {
                "title": title,
                "price": price,
                "url": url,
                "site": site,
                "ends_at": auction_end,
            }

            if hours_left <= 1 and not n1:
                print(f"[watcher] 1h reminder for: {title}")
                send_listing_alert(listing_dict, "Auktion endet in unter 1 Stunde!")
                db.set_notified(lid, flag_1h=True)

            elif hours_left <= 24 and not n24:
                print(f"[watcher] 24h reminder for: {title}")
                send_listing_alert(listing_dict, "Auktion endet in unter 24 Stunden")
                db.set_notified(lid, flag_24h=True)


if __name__ == "__main__":
    run()
