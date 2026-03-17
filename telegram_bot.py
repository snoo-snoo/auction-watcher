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
    site_label = listing.get("site", "").capitalize()
    title = listing.get("title", "–")
    price = listing.get("price") or "Kein Preis"
    url = listing.get("url", "")
    ends_at = listing.get("ends_at")
    remaining = _time_remaining(ends_at)

    lines = [
        f"🔔 <b>{reason}</b>",
        f"<b>{title}</b>",
        f"💶 {price}",
        f"🌐 {site_label}",
    ]
    if ends_at:
        lines.append(f"⏰ Endet in: {remaining}")
    lines.append(f"🔗 <a href=\"{url}\">Zum Inserat</a>")

    return send_message("\n".join(lines))


def send_suggestions(keyword: str, listings: list[dict]) -> bool:
    if not listings:
        return True
    header = f"🔍 Neue Treffer für <b>{keyword}</b> ({len(listings)} Inserat(e)):\n"
    chunks = [header]
    for i, l in enumerate(listings, 1):
        title = l.get("title", "–")
        price = l.get("price") or "Kein Preis"
        url = l.get("url", "")
        ends_at = l.get("ends_at")
        line = f"{i}. <b>{title}</b> – {price}"
        if ends_at:
            line += f" (endet in {_time_remaining(ends_at)})"
        line += f"\n   🔗 <a href=\"{url}\">{url[:60]}</a>"
        chunks.append(line)

    text = "\n".join(chunks)
    # Telegram max message length is 4096 chars; truncate if needed
    if len(text) > 4000:
        text = text[:3990] + "\n… (mehr im Browser)"
    return send_message(text)
