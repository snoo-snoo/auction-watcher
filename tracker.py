from datetime import datetime, timezone

import db
import willhaben
import aurena
import notifier


def search_all(query: str) -> list[dict]:
    results = []
    results += willhaben.search(query)
    results += aurena.search(query)
    return results


def add_to_watchlist(keyword: str) -> int:
    return db.add_keyword(keyword)


def show_watchlist():
    items = db.get_all_keywords()
    if not items:
        print("Watchlist is empty.")
        return
    print(f"\n{'ID':<5} {'Keyword':<30} {'Added'}")
    print("-" * 60)
    for item_id, keyword, added_at in items:
        print(f"{item_id:<5} {keyword:<30} {added_at[:19]}")


def remove_from_watchlist(item_id: int):
    items = {row[0]: row[1] for row in db.get_all_keywords()}
    if item_id not in items:
        print(f"No watchlist item with ID {item_id}.")
        return
    db.remove_keyword(item_id)
    print(f"Removed «{items[item_id]}» (ID {item_id}) from watchlist.")


def check_all():
    items = db.get_all_keywords()
    if not items:
        print("Watchlist is empty. Nothing to check.")
        return

    now = datetime.now(timezone.utc)

    for item_id, keyword, _ in items:
        print(f"\nChecking «{keyword}»…")
        results = search_all(keyword)

        if not results:
            print("  No results found.")
            continue

        new_count = 0
        for listing in results:
            is_new, notified_24h, notified_1h = db.upsert_listing(
                item_id,
                listing["site"],
                listing["title"],
                listing.get("price"),
                listing["url"],
                listing.get("auction_end"),
            )

            if is_new:
                new_count += 1
                notifier.notify_new_listing(keyword, listing)

        if new_count:
            print(f"  {new_count} new listing(s) found — Telegram notification sent.")

        # Auction end-time alerts
        rows = db.get_listings_for_keyword(item_id)
        for (
            listing_id, site, title, price, url,
            auction_end, notified_24h, notified_1h,
        ) in rows:
            if not auction_end:
                continue
            try:
                end_dt = datetime.fromisoformat(auction_end)
                if end_dt.tzinfo is None:
                    end_dt = end_dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue

            delta = (end_dt - now).total_seconds()
            hours_left = delta / 3600

            if delta <= 0:
                continue  # already ended

            if hours_left <= 1 and not notified_1h:
                notifier.notify_auction_ending(title, url, hours_left, urgent=True)
                db.set_notified(listing_id, flag_1h=True, flag_24h=True)
                print(f"  URGENT: auction ending in <1h — {title}")
            elif hours_left <= 24 and not notified_24h:
                notifier.notify_auction_ending(title, url, hours_left)
                db.set_notified(listing_id, flag_24h=True)
                print(f"  Alert: auction ending in {hours_left:.1f}h — {title}")
