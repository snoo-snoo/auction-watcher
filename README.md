# auction-watcher

Monitors **willhaben.at** and **aurena.at** for items on your watchlist and sends Telegram reminders before auctions end.

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Review / adjust credentials
nano config.py
```

`config.py` contains:
- `TELEGRAM_TOKEN` — your bot token from @BotFather
- `TELEGRAM_CHAT_ID` — your personal or group chat ID
- `DB_PATH` — SQLite database file path (default: `watchlist.db`)

The database is created automatically on first run.

---

## Usage

### Manage your watchlist

```bash
# Add a keyword
python cli.py add "Büroschrank"

# Show all keywords
python cli.py list

# Remove a keyword (also removes its tracked listings)
python cli.py remove "Büroschrank"
```

### Search

```bash
# One-shot search — prints results to terminal, does NOT save or notify
python cli.py search "Stehlampe"
```

### Run the watcher

```bash
# Run once — searches all keywords, saves new listings, sends Telegram messages
python cli.py watch
```

### Inspect tracked listings

```bash
python cli.py listings
```

---

## Automation with cron

Run the watcher every 30 minutes:

```cron
*/30 * * * * cd /path/to/auction-watcher && python cli.py watch >> watcher.log 2>&1
```

---

## Telegram notifications

The bot sends three types of messages:

| Trigger | Message |
|---|---|
| New listing found | Batch suggestion with title, price, link |
| Auction ends in < 24 h | Single alert (sent once) |
| Auction ends in < 1 h | Urgent alert (sent once) |

---

## Notes on site scraping

### willhaben.at

willhaben is a React/Next.js app. Plain HTTP requests get the server-side
rendered HTML, which includes a __NEXT_DATA__ JSON blob that the scraper
tries to parse first.

If results come back empty: willhaben may have changed its data structure.
Consider switching to Playwright for full JS rendering:

    pip install playwright && playwright install chromium

Then replace the requests.get(...) call in scraper_willhaben.py with a
Playwright page load — a comment in that file marks the exact location.

### aurena.at

aurena.at renders more of its content server-side. The scraper parses auction
end times from:
- data-ends-at / datetime HTML attributes
- German date strings ("17. März 2026, 14:30 Uhr")
- Relative strings ("endet in 2 Stunden")

---

## Project structure

```
config.py             — credentials and shared constants
db.py                 — SQLite setup and CRUD helpers
telegram_bot.py       — Telegram message sender
scraper_willhaben.py  — willhaben.at search
scraper_aurena.py     — aurena.at search
watcher.py            — main orchestration logic
cli.py                — command-line interface
requirements.txt      — Python dependencies
watchlist.db          — SQLite database (created on first run)
```
