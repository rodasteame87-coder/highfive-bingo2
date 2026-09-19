"""
HighFive Bingo - Telegram Bot + Mini App Backend

Render Start Command:
    gunicorn server:app

Required environment variables:
    BOT_TOKEN       = your Telegram bot token
    ADMIN_KEY       = random secret
    ADMIN_USER_ID   = your Telegram numeric user ID

Optional:
    APP_URL         = https://highfive-bingo2.onrender.com
    WEBHOOK_SECRET  = random webhook secret
"""

import hashlib
import hmac
import json
import os
import random
import threading
import time
from functools import wraps
from urllib.parse import parse_qsl

from flask import Flask, jsonify, request, send_from_directory
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


# ============================================================
# CONFIGURATION
# ============================================================

BASE = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    static_folder=BASE,
    static_url_path=""
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_KEY = os.environ.get("ADMIN_KEY", "change-this-admin-key").strip()

APP_URL = os.environ.get(
    "APP_URL",
    "https://highfive-bingo2.onrender.com"
).rstrip("/")

WEBHOOK_SECRET = os.environ.get(
    "WEBHOOK_SECRET",
    "highfive-bingo-secret"
).strip()

try:
    ADMIN_USER_ID = str(
        os.environ.get("ADMIN_USER_ID", "").strip()
    )
except Exception:
    ADMIN_USER_ID = ""


# ============================================================
# GAME STATE
# ============================================================

lock = threading.Lock()

game = {
    "running": False,
    "autoplay": False,

    "title": "HighFive Bingo",

    "message": "Join the game to receive your Bingo card.",

    "called": [],

    "players": {},

    "winners": [],

    "last_call": 0,

    "admin_chat_id": None,

    "call_interval": 5,
}


# ============================================================
# TELEGRAM API
# ============================================================

TELEGRAM_API = (
    f"https://api.telegram.org/bot{BOT_TOKEN}"
)


def telegram_api(method, data=None):
    """
    Call Telegram Bot API without requiring the requests package.
    """

    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN is missing.")
        return None

    if data is None:
        data = {}

    try:
        body = json.dumps(data).encode("utf-8")

        req = Request(
            f"{TELEGRAM_API}/{method}",
            data=body,
            headers={
                "Content-Type": "application/json"
            },
            method="POST",
        )

        with urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")

        result = json.loads(raw)

        if not result.get("ok"):
            print(
                "Telegram API error:",
                result
            )

        return result

    except HTTPError as e:
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            error_body = str(e)

        print(
            f"Telegram HTTP error {e.code}:",
            error_body
        )

    except URLError as e:
        print(
            "Telegram connection error:",
            e
        )

    except Exception as e:
        print(
            "Telegram API exception:",
            repr(e)
        )

    return None


def send_message(
    chat_id,
    text,
    reply_markup=None
):
    """
    Send a Telegram message.
    """

    if not chat_id:
        return None

    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }

    if reply_markup:
        data["reply_markup"] = reply_markup

    return telegram_api(
        "sendMessage",
        data
    )


def answer_callback_query(
    callback_query_id,
    text=None
):
    data = {
        "callback_query_id":
            callback_query_id
    }

    if text:
        data["text"] = text

    return telegram_api(
        "answerCallbackQuery",
        data
    )


# ============================================================
# TELEGRAM KEYBOARDS
# ============================================================

def bingo_keyboard():
    """
    Button that opens the Telegram Mini App.
    """

    return {
        "inline_keyboard": [
            [
                {
                    "text": "🎮 Open Bingo",
                    "web_app": {
                        "url": APP_URL
                    }
                }
            ]
        ]
    }


def admin_keyboard():
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🎮 Open Bingo",
                    "web_app": {
                        "url": APP_URL
                    }
                }
            ],
            [
                {
                    "text": "▶️ Start Game",
                    "callback_data": "admin_start"
                },
                {
                    "text": "⏹ Stop Game",
                    "callback_data": "admin_stop"
                }
            ],
            [
                {
                    "text": "🔢 Call Number",
                    "callback_data": "admin_call"
                },
                {
                    "text": "🤖 Autoplay",
                    "callback_data": "admin_autoplay"
                }
            ]
        ]
    }


# ============================================================
# ADMIN CHECK
# ============================================================

def is_admin(user_id):
    """
    Only ADMIN_USER_ID can control the game.
    """

    if not ADMIN_USER_ID:
        return False

    return str(user_id) == ADMIN_USER_ID


# ============================================================
# BINGO CARDS
# ============================================================

def make_card():
    """
    Standard 75-ball Bingo card.
    """

    columns = [
        random.sample(
            range(1, 16),
            5
        ),

        random.sample(
            range(16, 31),
            5
        ),

        random.sample(
            range(31, 46),
            5
        ),

        random.sample(
            range(46, 61),
            5
        ),

        random.sample(
            range(61, 76),
            5
        ),
    ]

    # Convert columns to row-major order.
    card = [
        columns[c][r]
        for r in range(5)
        for c in range(5)
    ]

    # FREE center.
    card[12] = 0

    return card


def is_winner(card, called):
    """
    Check rows, columns and diagonals.
    """

    called_set = set(called)

    marks = {
        i
        for i, number in enumerate(card)
        if i == 12 or number in called_set
    }

    lines = []

    # Rows
    for row in range(5):
        lines.append(
            {
                row * 5 + col
                for col in range(5)
            }
        )

    # Columns
    for col in range(5):
        lines.append(
            {
                row * 5 + col
                for row in range(5)
            }
        )

    # Diagonals
    lines.append(
        {0, 6, 12, 18, 24}
    )

    lines.append(
        {4, 8, 12, 16, 20}
    )

    return any(
        line <= marks
        for line in lines
    )


# ============================================================
# TELEGRAM INIT DATA VALIDATION
# ============================================================

def validate_telegram_init_data(init_data):
    """
    Validate Telegram Mini App initData.
    """

    if not init_data or not BOT_TOKEN:
        return None

    try:
        pairs = dict(
            parse_qsl(
                init_data,
                keep_blank_values=True
            )
        )

        received_hash = pairs.pop(
            "hash",
            None
        )

        if not received_hash:
            return None

        data_check_string = "\n".join(
            f"{key}={pairs[key]}"
            for key in sorted(pairs)
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode("utf-8"),
            hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(
            calculated_hash,
            received_hash
        ):
            return None

        auth_date = int(
            pairs.get(
                "auth_date",
                "0"
            )
        )

        # 24-hour validity.
        if time.time() - auth_date > 86400:
            return None

        user = json.loads(
            pairs.get(
                "user",
                "{}"
            )
        )

        return user

    except Exception as e:
        print(
            "Init data validation error:",
            repr(e)
        )
        return None


def current_user():
    return validate_telegram_init_data(
        request.headers.get(
            "X-Telegram-Init-Data",
            ""
        )
    )


def require_user(fn):

    @wraps(fn)
    def wrapper(*args, **kwargs):

        user = current_user()

        if not user:
            return jsonify(
                {
                    "error":
                        "Open this Mini App from Telegram."
                }
            ), 401

        request.telegram_user = user

        return fn(
            *args,
            **kwargs
        )

    return wrapper


# ============================================================
# WEB PAGES
# ============================================================

@app.get("/")
def index():
    return send_from_directory(
        BASE,
        "index.html"
    )


@app.get("/<path:path>")
def static_files(path):
    return send_from_directory(
        BASE,
        path
    )


# ============================================================
# MINI APP API
# ============================================================

@app.get("/api/state")
@require_user
def state():

    uid = str(
        request.telegram_user["id"]
    )

    with lock:

        player = game["players"].get(
            uid
        )

        card = (
            player["card"]
            if player
            else None
        )

        marked = []

        if player:

            marked = [
                number
                for number in player["card"]
                if number
                and number in game["called"]
            ]

        return jsonify(
            {
                "running":
                    game["running"],

                "autoplay":
                    game["autoplay"],

                "title":
                    game["title"],

                "message":
                    game["message"],

                "called":
                    game["called"],

                "last_call":
                    game["last_call"],

                "card":
                    card,

                "marked":
                    marked,

                "winners":
                    game["winners"],
            }
        )


@app.post("/api/join")
@require_user
def join():

    uid = str(
        request.telegram_user["id"]
    )

    name = request.telegram_user.get(
        "first_name",
        "Player"
    )

    with lock:

        if uid not in game["players"]:

            game["players"][uid] = {
                "name": name,
                "card": make_card(),
            }

        return jsonify(
            {
                "ok": True,

                "card":
                    game["players"][uid]["card"],

                "message":
                    "Joined successfully.",
            }
        )


@app.post("/api/claim")
@require_user
def claim():

    uid = str(
        request.telegram_user["id"]
    )

    with lock:

        player = game["players"].get(
            uid
        )

        if not player:

            return jsonify(
                {
                    "ok": False,
                    "message":
                        "Join the game first.",
                }
            ), 400

        if is_winner(
            player["card"],
            game["called"]
        ):

            if uid not in game["winners"]:

                game["winners"].append(
                    uid
                )

                # Notify admin.
                if game["admin_chat_id"]:

                    send_message(
                        game["admin_chat_id"],
                        (
                            "🎉 <b>BINGO!</b>\n\n"
                            f"Player: "
                            f"<b>{player['name']}</b>\n"
                            f"User ID: <code>{uid}</code>"
                        )
                    )

            return jsonify(
                {
                    "ok": True,
                    "message":
                        (
                            "🎉 BINGO! "
                            f"Congratulations, "
                            f"{player['name']}!"
                        )
                }
            )

        return jsonify(
            {
                "ok": False,
                "message":
                    "Not a winning line yet."
            }
        )


# ============================================================
# ADMIN HTTP API
# ============================================================

def admin_ok():

    return hmac.compare_digest(
        request.headers.get(
            "X-Admin-Key",
            ""
        ),
        ADMIN_KEY
    )


@app.post("/api/admin/start")
def admin_start():

    if not admin_ok():

        return jsonify(
            {
                "error":
                    "Unauthorized"
            }
        ), 401

    with lock:

        game["running"] = True
        game["autoplay"] = False

        game["title"] = (
            "Game is LIVE"
        )

        game["message"] = (
            "Numbers are being called."
        )

        game["called"] = []
        game["winners"] = []
        game["last_call"] = 0

    return jsonify(
        {
            "ok": True
        }
    )


@app.post("/api/admin/stop")
def admin_stop():

    if not admin_ok():

        return jsonify(
            {
                "error":
                    "Unauthorized"
            }
        ), 401

    with lock:

        game["running"] = False
        game["autoplay"] = False

        game["message"] = (
            "Game finished."
        )

    return jsonify(
        {
            "ok": True
        }
    )


@app.post("/api/admin/call")
def admin_call():

    if not admin_ok():

        return jsonify(
            {
                "error":
                    "Unauthorized"
            }
        ), 401

    number = call_number()

    if number is None:

        return
