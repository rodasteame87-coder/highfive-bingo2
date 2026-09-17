"""
Highfive Bingo Mini App backend.

Install:
    pip install flask gunicorn

Set environment variables:
    BOT_TOKEN=your Telegram bot token
    ADMIN_KEY=a-long-random-secret

Run locally:
    python server.py

For production, put this behind HTTPS (for example a VPS/reverse proxy).
Telegram Mini Apps should use an HTTPS URL.
"""

import hashlib
import hmac
import json
import os
import random
import threading
import time
from functools import wraps

from flask import Flask, jsonify, request, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE, static_url_path="")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
ADMIN_KEY = os.environ.get("ADMIN_KEY", "change-this-admin-key")

lock = threading.Lock()
game = {
    "running": False,
    "title": "Highfive Bingo",
    "message": "Join the game to receive a card.",
    "called": [],
    "players": {},       # telegram user id -> {"name": ..., "card": [...]}
    "winners": [],
    "last_call": 0,
}


def validate_telegram_init_data(init_data: str):
    """Validate Telegram.WebApp.initData using the bot token."""
    if not init_data or not BOT_TOKEN:
        return None

    try:
        pairs = {}
        for part in init_data.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                pairs[k] = v

        received_hash = pairs.pop("hash", None)
        if not received_hash:
            return None

        # Telegram WebApp validation:
        # secret_key = HMAC-SHA256(bot_token, key=b"WebAppData")
        secret_key = hmac.new(
            b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256
        ).digest()

        check_string = "\n".join(
            f"{k}={pairs[k]}" for k in sorted(pairs)
        )
        calculated = hmac.new(
            secret_key, check_string.encode(), hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated, received_hash):
            return None

        auth_date = int(pairs.get("auth_date", "0"))
        if time.time() - auth_date > 86400:
            return None

        user = json.loads(pairs.get("user", "{}"))
        return user
    except Exception:
        return None


def current_user():
    return validate_telegram_init_data(
        request.headers.get("X-Telegram-Init-Data", "")
    )


def require_user(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"error": "Open this Mini App from Telegram."}), 401
        request.telegram_user = user
        return fn(*args, **kwargs)
    return wrapper


def make_card():
    cols = [
        random.sample(range(1, 16), 5),
        random.sample(range(16, 31), 5),
        random.sample(range(31, 46), 5),
        random.sample(range(46, 61), 5),
        random.sample(range(61, 76), 5),
    ]
    # row-major 5x5
    card = [cols[c][r] for r in range(5) for c in range(5)]
    card[12] = 0  # FREE
    return card


def is_winner(card, called):
    called_set = set(called)
    marks = {i for i, n in enumerate(card) if i == 12 or n in called_set}

    lines = []
    for r in range(5):
        lines.append({r * 5 + c for c in range(5)})
    for c in range(5):
        lines.append({r * 5 + c for r in range(5)})
    lines += [
        {0, 6, 12, 18, 24},
        {4, 8, 12, 16, 20},
    ]
    return any(line <= marks for line in lines)


@app.get("/")
def index():
    return send_from_directory(BASE, "index.html")


@app.get("/<path:path>")
def static_files(path):
    return send_from_directory(BASE, path)


@app.get("/api/state")
@require_user
def state():
    uid = str(request.telegram_user["id"])
    with lock:
        p = game["players"].get(uid)
        return jsonify({
            "running": game["running"],
            "title": game["title"],
            "message": game["message"],
            "called": game["called"],
            "card": p["card"] if p else None,
            "marked": [
                n for n in (p["card"] if p else [])
                if n and n in game["called"]
            ],
        })


@app.post("/api/join")
@require_user
def join():
    uid = str(request.telegram_user["id"])
    name = request.telegram_user.get("first_name", "Player")
    with lock:
        if not game["running"]:
            # Allow joining before the host starts; card is reserved.
            pass
        if uid not in game["players"]:
            game["players"][uid] = {
                "name": name,
                "card": make_card(),
            }
        return jsonify({
            "ok": True,
            "card": game["players"][uid]["card"],
            "message": "Joined successfully.",
        })


@app.post("/api/claim")
@require_user
def claim():
    uid = str(request.telegram_user["id"])
    with lock:
        p = game["players"].get(uid)
        if not p:
            return jsonify({"ok": False, "message": "Join the game first."}), 400
        if is_winner(p["card"], game["called"]):
            if uid not in game["winners"]:
                game["winners"].append(uid)
            return jsonify({
                "ok": True,
                "message": f"🎉 BINGO! Congratulations, {p['name']}!"
            })
        return jsonify({
            "ok": False,
            "message": "Not a winning line yet."
        })


def admin_ok():
    return hmac.compare_digest(
        request.headers.get("X-Admin-Key", ""),
        ADMIN_KEY
    )


@app.post("/api/admin/start")
def admin_start():
    if not admin_ok():
        return jsonify({"error": "Unauthorized"}), 401
    with lock:
        game["running"] = True
        game["title"] = "Game is LIVE"
        game["message"] = "Numbers are being called."
        game["called"] = []
        game["winners"] = []
        game["last_call"] = 0
    return jsonify({"ok": True})


@app.post("/api/admin/stop")
def admin_stop():
    if not admin_ok():
        return jsonify({"error": "Unauthorized"}), 401
    with lock:
        game["running"] = False
        game["message"] = "Game finished."
    return jsonify({"ok": True})


@app.post("/api/admin/call")
def admin_call():
    if not admin_ok():
        return jsonify({"error": "Unauthorized"}), 401
    with lock:
        if not game["running"]:
            return jsonify({"error": "Game is not running"}), 400
        remaining = [n for n in range(1, 76) if n not in game["called"]]
        if not remaining:
            game["running"] = False
            return jsonify({"ok": True, "finished": True})
        n = random.choice(remaining)
        game["called"].append(n)
        game["last_call"] = n
        return jsonify({"ok": True, "number": n, "letter": "BINGO"[
            min((n - 1) // 15, 4)
        ]})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), debug=False)
