# ONEUSDT One-Shot Net Est Grid Bot

Python bot for Binance USD-M Futures Demo with Telegram notifications and Railway deployment.

## Logic

- Exchange: Binance Futures Demo by default.
- Symbol: `ONEUSDT`.
- Strategy: one-shot grid.
- Places nearest `BUY LONG` below current bid and nearest `SELL SHORT` above current ask.
- After the first entry is filled, cancels the opposite entry.
- Does **not** place TP limit orders.
- Closes only by `Net est`:
  - `Net est >= +0.10 USDT` -> close in profit.
  - `Net est <= -0.40 USDT` -> stop close.
- Sends Telegram notifications on start, entry, take, stop, API downtime, and summary.

## Files

- `main.py` — bot.
- `.env.example` — example environment variables.
- `requirements.txt` — dependencies.
- `railway.toml` — Railway start command.
- `scripts/get_telegram_chat_id.py` — helper to find Telegram chat ID.

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env` with your Binance Demo API key/secret and Telegram token/chat ID.

Run:

```bash
python main.py
```

## Telegram setup

1. Open Telegram and message `@BotFather`.
2. Create bot with `/newbot`.
3. Copy bot token to `TELEGRAM_BOT_TOKEN`.
4. Send any message to your new bot.
5. Run:

```bash
python scripts/get_telegram_chat_id.py
```

6. Copy `chat.id` to `TELEGRAM_CHAT_ID`.

## Railway setup

1. Push this project to GitHub.
2. In Railway, create a new project from GitHub repository.
3. Add all variables from `.env.example` in Railway Variables.
4. Deploy. Railway will use `python main.py` from `railway.toml`.

## Safety

This project is configured for Binance Futures Demo by default. Do not use real keys until demo testing is stable.
Never commit `.env` to GitHub.
