# 🔨 auction-watcher

> Automatically monitors **willhaben.at** and **aurena.at** for items on your watchlist and sends Telegram alerts before auctions end.

---

## ✨ Features

- 🔍 **Keyword search** across willhaben.at and aurena.at
- 📬 **Telegram notifications** — new listings, 24h warning, 1h urgent alert
- 💾 **SQLite watchlist** — persist keywords and tracked listings
- 🔐 **Authenticated aurena API** — uses official GraphQL endpoint
- ⚙️ **Cron-ready** — run every 30 minutes, fully unattended

---

## 🚀 Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Review credentials
nano config.py        # Telegram token + chat ID
nano aurena_auth.py   # aurena login (if needed)
```

`config.py` contains:
| Key | Description |
|---|---|
| `TELEGRAM_TOKEN` | Bot token from [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_CHAT_ID` | Your personal chat ID |
| `DB_PATH` | SQLite database path (default: `watchlist.db`) |

---

## 📖 Usage

### Manage your watchlist

```bash
python cli.py add "Büroschrank"       # Add a keyword
python cli.py list                    # Show all keywords
python cli.py remove "Büroschrank"    # Remove keyword + its listings
```

### Search (one-shot, no saving)

```bash
python cli.py search "Holzfenster"
```

### Run the watcher

```bash
python cli.py watch      # Search all keywords, save new results, send Telegram messages
python cli.py listings   # Show currently tracked listings
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
| New listing found | Title, price, link |
| Auction ends in < 24 h | ⚠️ Single alert |
| Auction ends in < 1 h | 🚨 Urgent alert |

---

## 🏗️ Architecture

```
auction-watcher/
│
├── cli.py                 CLI entry point (add / remove / search / watch / listings)
├── watcher.py             Main orchestration logic
│
├── scraper_willhaben.py   willhaben.at scraper (Next.js / __NEXT_DATA__ parsing)
├── scraper_aurena.py      aurena.at scraper (authenticated REST API)
├── aurena_auth.py         aurena GraphQL login + token caching
│
├── db.py                  SQLite helpers (watchlist + listings)
├── telegram_bot.py        Telegram message sender
├── config.py              Credentials + constants
└── requirements.txt       Python dependencies
```

---

## 🔧 Technical Notes

### willhaben.at

willhaben is a **React/Next.js** app. The scraper parses the `__NEXT_DATA__` JSON blob embedded server-side — this contains pre-rendered search results including SEO-friendly URLs.

If results come back empty, willhaben may have changed their data structure. The fallback is switching to [Playwright](https://playwright.dev/) for full JS rendering (a comment in `scraper_willhaben.py` marks the integration point).

### aurena.at

aurena is an **Angular SPA** backed by a proprietary GraphQL + REST API. The scraper:

1. Authenticates via GraphQL mutation (`login`) with base64-encoded credentials
2. Fetches all active auctions via REST package endpoint
3. Filters by keyword across title, category, and description fields

> **Note:** aurena organizes items as *auction events* (e.g. "Lagerauflösung Wien"), not individual listings like willhaben. Keyword matches are at the auction level.

---

## 📦 Dependencies

```
requests
beautifulsoup4
lxml
```

Install with:
```bash
pip install -r requirements.txt
```

---

## 📄 License

MIT — do whatever you want with it.
