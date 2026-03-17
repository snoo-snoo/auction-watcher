import sys
from datetime import datetime, timezone
import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"


def send_message(text: str) -> bool:
    try:
        resp = requests.post(API_URL, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[telegram] Error sending message: {e}", file=sys.stderr)
        return False


def _time_remaining(ends_at_iso: str | None) -> str:
    if not ends_at_iso:
        return "unbekannt"
    try:
        ends = datetime.fromisoformat(ends_at_iso)
        if ends.tzinfo is None:
            ends = ends.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = ends - now
        if delta.total_seconds() <= 0:
            return "bereits beendet"
        hours, rem = divmod(int(delta.total_seconds()), 3600)
        minutes = rem // 60
        if hours >= 24:
            days = hours // 24
            return f"{days}d {hours % 24}h"
        return f"{hours}h {minutes}m"
    except Exception:
        return ends_at_iso


def send_listing_alert(listing: dict, reason: str) -> bool:
    title = listing.get("title", "–")
    url = listing.get("url", "")
    price = listing.get("price") or "–"
    msg = f"{reason}\n<b>{title}</b> · {price}\n🔗 {url}"
    return send_message(msg)


def send_suggestions(keyword: str, listings: list[dict]) -> bool:
    if not listings:
        return True

    MAX_LEN = 4000
    header = f"🔍 <b>{keyword}</b> — {len(listings)} neue Inserate:\n"

    lines = []
    for l in listings:
        title = (l.get("title") or "–").replace("<", "&lt;").replace(">", "&gt;")
        price = l.get("price") or "–"
        url = l.get("url", "")
        lines.append(f"• <a href=\"{url}\">{title}</a> · {price}")

    current = header
    part = 1
    for line in lines:
        candidate = current + "\n" + line
        if len(candidate) > MAX_LEN:
            send_message(current)
            current = f"🔍 <b>{keyword}</b> (Forts. {part}):\n" + line
            part += 1
        else:
            current = candidate

    if current:
        send_message(current)
    return True
