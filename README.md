# Highfive Bingo Telegram Mini App

This package contains a mobile-friendly Telegram Bingo Mini App and a small Flask backend.

## Important

The Mini App URL must be publicly reachable over **HTTPS** when configured in BotFather.

Do NOT put your Telegram bot token inside `index.html` or `app.js`.

## Files

- `index.html` — Mini App interface
- `style.css` — mobile-first design
- `app.js` — Telegram integration + API polling
- `server.py` — Bingo game API and Telegram init-data validation
- `requirements.txt` — Python dependencies

## 1. Install

```bash
pip install -r requirements.txt
```

## 2. Set secrets

Set these environment variables on the server:

```text
BOT_TOKEN=YOUR_REAL_BOTFATHER_TOKEN
ADMIN_KEY=MAKE_A_LONG_RANDOM_SECRET
```

Never publish the real BOT_TOKEN.

## 3. Test locally

```bash
python server.py
```

Open the site in a browser to check the UI. The real API requires a valid Telegram Mini App session, so the useful multiplayer test should be launched from Telegram.

## 4. Put it online

Use a hosting provider that gives you an HTTPS URL. Upload all files and run:

```bash
gunicorn -w 1 -b 0.0.0.0:8080 server:app
```

For a real production game, use a proper HTTPS reverse proxy and persistent storage instead of this in-memory game state.

## 5. Configure BotFather

In @BotFather:

Bot Settings -> Menu Button -> Configure Menu Button

Set the button text, for example:

```text
Bingo
```

and enter your public HTTPS URL:

```text
https://YOUR-DOMAIN.example/
```

Do not enter a Pydroid `localhost` URL.

## 6. Start / call numbers

The included backend exposes admin endpoints. Example:

Start:
```bash
curl -X POST https://YOUR-DOMAIN.example/api/admin/start \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"
```

Call one number:
```bash
curl -X POST https://YOUR-DOMAIN.example/api/admin/call \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"
```

Stop:
```bash
curl -X POST https://YOUR-DOMAIN.example/api/admin/stop \
  -H "X-Admin-Key: YOUR_ADMIN_KEY"
```

The Mini App polls `/api/state` every 2.5 seconds, so players see called numbers update.

## 7. Connecting your existing Python Telegram bot

Your existing bot can call these same backend endpoints for `/startgame`, `/call`, `/stopgame`, etc. Keep the Telegram bot token only in the Python bot/server environment.

The backend validates Telegram `initData` before accepting player actions.

## Current game rules

- 75-ball Bingo
- 5 x 5 card
- B: 1–15
- I: 16–30
- N: 31–45
- G: 46–60
- O: 61–75
- Center square is FREE
- Winner is any complete row, column, or diagonal
- Multiple players can join the same running server instance

## Production note

This is a working starter implementation, but it uses in-memory state. If the process restarts, the game/cards disappear. For a paid/public Bingo service, add a database (SQLite/PostgreSQL), an authenticated host/admin panel, rate limiting, and persistent game IDs.
