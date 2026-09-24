# Smart Adaptive Neutral Bot v6.1.1 — Clean Telegram

Зміни цієї версії:

- Торгова логіка залишена від v6.1 env-safe.
- Telegram повідомлення переписані українською і структуровано.
- Прибрано зайві Telegram-повідомлення про кожен аналіз/skip/reprice.
- Залишено важливі події: старт, підготовка входу, відкриття позиції, TP-ордер, статус позиції, закриття, підсумок.
- `TELEGRAM_STATUS_EVERY_SECONDS=0` вимикає періодичні статуси.

## LIVE запуск

Для реальної біржі в Railway Variables потрібно явно поставити:

```env
BINANCE_BASE_URL=https://fapi.binance.com
FORCE_DEMO_ONLY=false
```

Для першого реального тесту краще починати малим розміром:

```env
ORDER_NOTIONAL_USDT=50
LEVERAGE=3
```

Після перевірки логів, ордерів і фактичних комісій можна збільшувати обсяг.

## Файли

- `main.py` — основний бот
- `requirements.txt` — залежності
- `.env.example` — приклад змінних
- `railway.toml` — Railway конфіг
