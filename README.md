# 🔨 auction-watcher

> Automatically monitors **willhaben.at** and **aurena.at** for items on your watchlist and sends Telegram alerts before auctions end. Includes a local web dashboard for managing everything.

---

## ✨ Features

- 🔍 **Keyword search** across willhaben.at and aurena.at
- 🔗 **Link tracking** — paste any listing URL to add it to your watchlist and instantly find similar offers for price comparison
- 🖼️ **Thumbnails** — listing images in the web dashboard
- 💶 **aurena pricing** — shows current highest bid + 18% Provision + 20% MwSt = real total price
- 📬 **Telegram notifications** — new listings, 24h warning, 1h urgent alert
- 💾 **SQLite watchlist** — persist keywords and tracked listings
- 🔐 **Authenticated aurena API** — uses official GraphQL endpoint
- 🌐 **Local web dashboard** — mobile-first dark UI, manage everything in the browser
- ⚙️ **Cron-ready** — run every 30 minutes, fully unattended

---

## 🚀 Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy and fill in credentials
cp .env.example .env
nano .env
```

`.env` keys:
| Key | Description |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Your personal chat ID |
| `AURENA_EMAIL` | aurena.at account email |
| `AURENA_PASSWORD` | aurena.at account password |
| `DB_PATH` | SQLite database path (default: `watchlist.db`) |

---

## 🌐 Web Dashboard

Start the local dashboard:

```bash
python web.py
```

Then open **http://localhost:5000** in your browser (also accessible from your phone on the same network).

**Dashboard features:**
- 📋 All watchlist keywords with their listings and thumbnails
- ➕ Add keywords or paste a listing URL directly (FAB button)
- 🗑 Remove keywords or individual listings
- 🔔 Toggle auction end alerts per listing
- ↻ Trigger a manual search run from the browser

---

## 📖 CLI Usage

### Manage your watchlist

```bash
python cli.py add "Büroschrank"       # Add a keyword
python cli.py list                    # Show all keywords
python cli.py remove "Büroschrank"    # Remove keyword + its listings
python cli.py listings                # Show all tracked listings
```

### Search (one-shot, no saving)

```bash
python cli.py search "Holzfenster"
```

### Track a listing URL

```bash
python cli.py track "https://www.willhaben.at/iad/..."
python cli.py track "https://www.aurena.at/posten/12345/..."
```

Fetches the listing, extracts keywords, searches for similar offers sorted by price, and adds the keyword to your watchlist. Use `--no-watch` to skip the watchlist addition.

### Run the watcher

```bash
python cli.py watch      # Search all keywords, save new results, send Telegram messages
```

---

## ⏰ Automation

Run every 30 minutes via cron:

```cron
*/30 * * * * cd /path/to/auction-watcher && python cli.py watch >> watcher.log 2>&1
```

---

## 📲 Telegram Notifications

| Trigger | Message |
|---|---|
| New listing found | Title, price, thumbnail link |
| Auction ends in < 24 h | ⚠️ Single alert |
| Auction ends in < 1 h | 🚨 Urgent alert |

---

## 💶 aurena Pricing

aurena lots are displayed with the **real total cost**:

```
(current bid + 18% Provision) × 1.20 MwSt
```

Example: current bid €20 → **~€28 total**

---

## 🏗️ Architecture

```
auction-watcher/
│
├── web.py                 Local Flask web dashboard
├── cli.py                 CLI entry point (add / remove / search / track / watch / listings)
├── watcher.py             Main orchestration logic (for cron)
│
├── scraper_willhaben.py   willhaben.at scraper (Next.js / __NEXT_DATA__ parsing)
├── scraper_aurena.py      aurena.at scraper (authenticated REST API)
├── aurena_auth.py         aurena GraphQL login + token caching
├── link_watch.py          URL tracker: fetch listing, extract keywords, find similar
│
├── db.py                  SQLite helpers (watchlist + listings + images)
├── telegram_bot.py        Telegram message sender (chunked for long lists)
├── config.py              Credentials + constants (via .env)
│
├── templates/index.html   Web dashboard template
├── .env.example           Environment variable template
└── requirements.txt       Python dependencies
```

---

## 🔧 Technical Notes

### willhaben.at

willhaben is a **React/Next.js** app. The scraper parses the `__NEXT_DATA__` JSON blob embedded server-side — this contains pre-rendered search results including SEO-friendly URLs and thumbnail images.

If results come back empty, willhaben may have changed their data structure. The fallback is switching to [Playwright](https://playwright.dev/) for full JS rendering (a comment in `scraper_willhaben.py` marks the integration point).

### aurena.at

aurena is an **Angular SPA** backed by a proprietary GraphQL + REST API. The scraper:

1. Authenticates via GraphQL mutation (`login`) with base64-encoded credentials
2. Fetches all active auctions, pre-filtered by category relevance to the keyword
3. For each candidate auction, locates the first lot ID using a global ID range estimation:
   - Aurena lot IDs are globally sequential across all auctions
   - A known anchor (auction 17515 → lot 4302118) is used to estimate ID ranges
   - First-lot IDs are cached in SQLite to avoid repeated probing
4. Fetches all lots in batches of 96 and filters by keyword against title + description
5. Returns individual `/posten/` URLs with current bid price + real total cost

**Pricing:** `(current bid + 18% Provision) × 1.20 MwSt` — the real amount you pay.

**Blacklist:** Deleted listings are permanently blocked and never re-added on future crawls.

**Lot refresh:** On every `watch` run, current bid prices for tracked aurena lots are updated.

---

## 📦 Dependencies

```
requests
beautifulsoup4
lxml
python-dotenv
flask
```

Install with:
```bash
pip install -r requirements.txt
```

---

## 📄 License

MIT — do whatever you want with it.
