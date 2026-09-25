# ONE Grid Bot — v6.1.2 LIVE SAFE 24/7

Що змінено:

- менше REST-запитів до Binance;
- нормальний backoff після 429 / 418;
- TP LIMIT не спамить: за замовчуванням 1 спроба;
- Telegram тільки по важливих подіях;
- режим 24/7: `TOTAL_RUNTIME_SECONDS=0`;
- якщо є відкрита позиція після рестарту, бот приймає її під контроль, а не відкриває нову;
- `CLOSE_ON_START=false` за замовчуванням, щоб не закривати позицію при redeploy.

## Мінімальні змінні Railway для LIVE

```env
BINANCE_BASE_URL=https://fapi.binance.com
FORCE_DEMO_ONLY=false
CLOSE_ON_START=false
CLOSE_ON_EXIT=false
TOTAL_RUNTIME_SECONDS=0

SYMBOL=DOGEUSDT
ORDER_NOTIONAL_USDT=50
LEVERAGE=3

TAKE_NET_PROFIT=0.10
TAKE_EXCHANGE_UPNL=0.15
EXCHANGE_TAKE_MIN_NET=0.02
MAX_CYCLE_LOSS=-0.30

CHECK_INTERVAL_SECONDS=2
ANALYSIS_REFRESH_SECONDS=60
REPRICE_ENTRY_SECONDS=30
PRINT_INTERVAL_SECONDS=15
TELEGRAM_STATUS_EVERY_SECONDS=0

API_RETRY_SLEEP_SECONDS=30
API_RATE_LIMIT_SLEEP_SECONDS=60
API_BAN_SLEEP_SECONDS=300
API_MAX_BACKOFF_SECONDS=600

USE_TP_LIMIT_ORDER=true
TP_LIMIT_MAX_ATTEMPTS=1
TP_LIMIT_RETRY_SECONDS=300
```

Для першого live-тесту не став великий обсяг. Спочатку перевір 10–20 циклів на маленькому розмірі.
