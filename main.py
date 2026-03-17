#!/usr/bin/env python3
"""
CLI entry point for the auction/listing tracker.

Usage:
  python main.py search "Büroschrank"
  python main.py watchlist
  python main.py check
  python main.py remove <id>
"""

import sys

import db
import tracker


def cmd_search(query: str):
    print(f"\nSearching for «{query}»…\n")
    results = tracker.search_all(query)

    if not results:
        print("No results found on either site.")
        return

    for i, item in enumerate(results, 1):
        ae = f"  [ends: {item['auction_end'][:16]}]" if item.get("auction_end") else ""
        print(f"  [{i:>2}] [{item['site']:>9}] {item['title'][:55]:<55} | {item.get('price','N/A'):>12}{ae}")
        print(f"        {item['url']}")

    print()
    raw = input("Add keyword to watchlist? Enter keyword (or leave blank to skip): ").strip()
    if raw:
        wid = tracker.add_to_watchlist(raw)
        print(f"Added «{raw}» to watchlist (ID {wid}).")
    else:
        print("Nothing added.")


def cmd_watchlist():
    tracker.show_watchlist()


def cmd_check():
    tracker.check_all()


def cmd_remove(item_id_str: str):
    try:
        item_id = int(item_id_str)
    except ValueError:
        print(f"Invalid ID: {item_id_str!r}. Must be an integer.")
        sys.exit(1)
    tracker.remove_from_watchlist(item_id)


def usage():
    print(__doc__)
    sys.exit(1)


def main():
    db.init_db()

    args = sys.argv[1:]
    if not args:
        usage()

    cmd = args[0]

    if cmd == "search":
        if len(args) < 2:
            print("Usage: python main.py search <query>")
            sys.exit(1)
        cmd_search(" ".join(args[1:]))

    elif cmd == "watchlist":
        cmd_watchlist()

    elif cmd == "check":
        cmd_check()

    elif cmd == "remove":
        if len(args) < 2:
            print("Usage: python main.py remove <id>")
            sys.exit(1)
        cmd_remove(args[1])

    else:
        print(f"Unknown command: {cmd!r}")
        usage()


if __name__ == "__main__":
    main()
