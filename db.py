import sqlite3
from datetime import datetime
from config import DB_PATH


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wishlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                added_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS found_listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wishlist_id INTEGER NOT NULL,
                site TEXT NOT NULL,
                title TEXT NOT NULL,
                price TEXT,
                url TEXT NOT NULL UNIQUE,
                auction_end TEXT,
                image_url TEXT,
                location TEXT,
                distance_km REAL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                notified_24h INTEGER DEFAULT 0,
                notified_1h INTEGER DEFAULT 0,
                FOREIGN KEY (wishlist_id) REFERENCES wishlist_items(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS blacklist (
                url TEXT PRIMARY KEY,
                blocked_at TEXT NOT NULL
            )
        """)
        # Migrations for existing DBs
        for col, typedef in [("image_url", "TEXT"), ("location", "TEXT"), ("distance_km", "REAL")]:
            try:
                conn.execute(f"ALTER TABLE found_listings ADD COLUMN {col} {typedef}")
                conn.commit()
            except Exception:
                pass
        conn.commit()


def add_keyword(keyword: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO wishlist_items (keyword, added_at) VALUES (?, ?)",
            (keyword, datetime.utcnow().isoformat()),
        )
        conn.commit()
        return cur.lastrowid


def get_all_keywords():
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, keyword, added_at FROM wishlist_items ORDER BY id"
        ).fetchall()


def remove_keyword(item_id: int):
    with get_conn() as conn:
        conn.execute("DELETE FROM found_listings WHERE wishlist_id = ?", (item_id,))
        conn.execute("DELETE FROM wishlist_items WHERE id = ?", (item_id,))
        conn.commit()


def upsert_listing(wishlist_id, site, title, price, url, auction_end, image_url=None, location=None, distance_km=None):
    now = datetime.utcnow().isoformat()
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, notified_24h, notified_1h FROM found_listings WHERE url = ?",
            (url,),
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE found_listings
                   SET last_seen=?, price=?, auction_end=?,
                       image_url=COALESCE(?, image_url),
                       location=COALESCE(?, location),
                       distance_km=COALESCE(?, distance_km)
                   WHERE url=?""",
                (now, price, auction_end, image_url, location, distance_km, url),
            )
            conn.commit()
            return False, existing[1], existing[2]
        else:
            conn.execute(
                """INSERT INTO found_listings
                   (wishlist_id, site, title, price, url, auction_end, image_url, location, distance_km, first_seen, last_seen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (wishlist_id, site, title, price, url, auction_end, image_url, location, distance_km, now, now),
            )
            conn.commit()
            return True, 0, 0


def get_listings_for_keyword(wishlist_id):
    with get_conn() as conn:
        return conn.execute(
            """SELECT id, site, title, price, url, auction_end, notified_24h, notified_1h, image_url, location, distance_km
               FROM found_listings WHERE wishlist_id = ?""",
            (wishlist_id,),
        ).fetchall()


def blacklist_url(url: str):
    """Add a URL to the blacklist so it's never re-added."""
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO blacklist (url, blocked_at) VALUES (?, datetime('now'))",
            (url,),
        )
        conn.commit()


def is_blacklisted(url: str) -> bool:
    with get_conn() as conn:
        return conn.execute(
            "SELECT 1 FROM blacklist WHERE url = ?", (url,)
        ).fetchone() is not None


def set_notified(listing_id, flag_24h=None, flag_1h=None):
    with get_conn() as conn:
        if flag_24h is not None:
            conn.execute(
                "UPDATE found_listings SET notified_24h=? WHERE id=?",
                (int(flag_24h), listing_id),
            )
        if flag_1h is not None:
            conn.execute(
                "UPDATE found_listings SET notified_1h=? WHERE id=?",
                (int(flag_1h), listing_id),
            )
        conn.commit()
