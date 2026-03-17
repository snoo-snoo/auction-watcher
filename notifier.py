import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"


def send(message: str):
    """Send a Telegram message. Silently logs errors."""
    try:
        resp = requests.post(
            API_URL,
            json={
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
            },
            timeout=10,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"[notifier] Telegram error: {e}")


def notify_new_listing(keyword: str, listing: dict):
    site = listing["site"].capitalize()
    title = listing["title"]
    price = listing.get("price", "N/A")
    url = listing["url"]
    msg = (
        f"🔔 <b>New listing for «{keyword}»</b>\n"
        f"📌 {site}: {title}\n"
        f"💶 {price}\n"
        f"🔗 {url}"
    )
    send(msg)


def notify_auction_ending(title: str, url: str, hours_left: float, urgent: bool = False):
    icon = "🚨" if urgent else "⏰"
    h = int(hours_left)
    m = int((hours_left - h) * 60)
    time_str = f"{h}h {m}m" if h else f"{m}m"
    msg = (
        f"{icon} <b>Auction ending in {time_str}</b>\n"
        f"📦 {title}\n"
        f"🔗 {url}"
    )
    send(msg)
