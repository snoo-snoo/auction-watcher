"""
web.py — Local web dashboard for auction-watcher

Run with:
    python web.py

Then open: http://localhost:5000
"""

from flask import Flask, render_template, request, redirect, url_for, jsonify
import db
from scraper_willhaben import search_willhaben
from scraper_aurena import search_aurena
from link_watch import watch_link
from watcher import run as run_watcher
import threading

app = Flask(__name__)
db.init_db()


def _get_dashboard_data():
    keywords = db.get_all_keywords()
    sections = []
    for kw_id, keyword, added_at in keywords:
        rows = db.get_listings_for_keyword(kw_id)
        listings = []
        for row in rows:
            lid, site, title, price, url, auction_end, n24, n1, image_url, location, dist_km = row
            listings.append({
                "id": lid,
                "site": site,
                "title": title,
                "price": price or "–",
                "url": url,
                "auction_end": auction_end,
                "notified_24h": bool(n24),
                "notified_1h": bool(n1),
                "image_url": image_url,
                "location": location,
                "distance_km": dist_km,
            })
        sections.append({
            "id": kw_id,
            "keyword": keyword,
            "added_at": added_at[:10],
            "listings": listings,
        })
    return sections


@app.route("/")
def index():
    sections = _get_dashboard_data()
    return render_template("index.html", sections=sections)


@app.route("/keyword/add", methods=["POST"])
def add_keyword():
    keyword = request.form.get("keyword", "").strip()
    if keyword:
        db.add_keyword(keyword)
    return redirect(url_for("index"))


@app.route("/keyword/<int:kw_id>/delete", methods=["POST"])
def delete_keyword(kw_id):
    db.remove_keyword(kw_id)
    return redirect(url_for("index"))


@app.route("/listing/<int:listing_id>/delete", methods=["POST"])
def delete_listing(listing_id):
    with db.get_conn() as conn:
        conn.execute("DELETE FROM found_listings WHERE id = ?", (listing_id,))
        conn.commit()
    return redirect(url_for("index"))


@app.route("/listing/<int:listing_id>/alert", methods=["POST"])
def toggle_alert(listing_id):
    """Toggle 24h/1h alert flags for a listing."""
    action = request.form.get("action", "reset")
    if action == "reset":
        db.set_notified(listing_id, flag_24h=False, flag_1h=False)
    elif action == "mute":
        db.set_notified(listing_id, flag_24h=True, flag_1h=True)
    return redirect(url_for("index"))


@app.route("/api/watch", methods=["PUT"])
def api_watch():
    """
    PUT /api/watch
    Add a keyword or listing URL to the watchlist.

    Body (JSON):
      { "keyword": "Holzfenster" }
      { "url": "https://www.willhaben.at/..." }
      { "url": "...", "keyword": "override keyword" }

    Returns JSON with result and (for URLs) similar listings.
    """
    data = request.get_json(force=True, silent=True) or {}
    url = data.get("url", "").strip()
    keyword = data.get("keyword", "").strip()

    if url:
        result = watch_link(url)
        if "error" in result:
            return jsonify({"ok": False, "error": result["error"]}), 400
        return jsonify({
            "ok": True,
            "listing": result["listing"],
            "keyword_added": result["search_term"],
            "similar_count": len(result["similar"]),
            "similar": result["similar"][:10],
        })
    elif keyword:
        row_id = db.add_keyword(keyword)
        return jsonify({"ok": True, "keyword": keyword, "id": row_id})
    else:
        return jsonify({"ok": False, "error": "Provide 'url' or 'keyword'"}), 400


@app.route("/watch", methods=["POST"])
def trigger_watch():
    """Run the watcher in background and redirect back."""
    def _run():
        run_watcher()
    threading.Thread(target=_run, daemon=True).start()
    return redirect(url_for("index") + "?refreshing=1")


@app.route("/track", methods=["POST"])
def track_url():
    url = request.form.get("url", "").strip()
    if not url:
        return redirect(url_for("index"))
    result = watch_link(url)
    sections = _get_dashboard_data()
    return render_template("index.html", sections=sections, track_result=result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
