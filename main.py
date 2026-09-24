import os
import time
import hmac
import hashlib
import re
import requests
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP, ROUND_CEILING, InvalidOperation
from datetime import datetime, timezone
from urllib.parse import urlencode
from typing import Any, Dict, Optional, List

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


# ============================================================
# CONFIG HELPERS
# ============================================================

def env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _clean_number_env(name: str, default: str) -> str:
    """
    Railway variables sometimes get pasted with commas, quotes, comments,
    or even as `NAME=value`. This sanitizer prevents startup crashes and
    extracts the first decimal-looking number.
    Examples accepted: 0.30, 0,30, "0.30", EXCHANGE_TAKE_MIN_NET=0.30, 0.30 # note.
    """
    raw = os.getenv(name)
    raw = default if raw is None or not raw.strip() else raw.strip()
    raw = raw.splitlines()[0].strip()
    if "=" in raw:
        raw = raw.split("=", 1)[1].strip()
    raw = raw.split("#", 1)[0].strip().strip('"').strip("'").replace(",", ".")

    match = re.search(r"[-+]?\d+(?:\.\d+)?", raw)
    if not match:
        print(f"⚠️ Bad numeric Railway variable {name}={raw!r}. Using default {default}.", flush=True)
        return default
    return match.group(0)


def env_decimal(name: str, default: str) -> Decimal:
    cleaned = _clean_number_env(name, default)
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        print(f"⚠️ Bad decimal Railway variable {name}={cleaned!r}. Using default {default}.", flush=True)
        return Decimal(default)


def env_int(name: str, default: str) -> int:
    return int(Decimal(_clean_number_env(name, default)))


def env_float(name: str, default: str) -> float:
    return float(Decimal(_clean_number_env(name, default)))


def env_bool(name: str, default: str = "false") -> bool:
    return env_str(name, default).lower() in {"1", "true", "yes", "y", "on"}


# ============================================================
# USER CONFIG — CHANGE VIA .env / RAILWAY VARIABLES
# ============================================================

BASE_URL = env_str("BINANCE_BASE_URL", "https://demo-fapi.binance.com")  # DEMO by default
SYMBOL = env_str("SYMBOL", "ONEUSDT")

LOWER_PRICE = env_decimal("LOWER_PRICE", "0.0023")
UPPER_PRICE = env_decimal("UPPER_PRICE", "0.0040")
GRID_COUNT = env_int("GRID_COUNT", "40")  # 40 cells = 41 price levels

MARGIN_BUDGET_USDT = env_decimal("MARGIN_BUDGET_USDT", "100")
LEVERAGE = env_int("LEVERAGE", "10")
ORDER_NOTIONAL_USDT = env_decimal("ORDER_NOTIONAL_USDT", "25")
ACTIVE_LEVELS_EACH_SIDE = env_int("ACTIVE_LEVELS_EACH_SIDE", "1")

# Entry placement: 0.0001 = 0.01% from current bid/ask.
# LONG is placed below best bid, SHORT is placed above best ask.
ENTRY_OFFSET_PCT = env_decimal("ENTRY_OFFSET_PCT", "0.0001")

# Adaptive entry: while no position is filled, refresh both entry orders around live bid/ask.
# This prevents old orders from standing far away after the market moves.
REPRICE_ENTRY_SECONDS = env_float("REPRICE_ENTRY_SECONDS", "10")
REPRICE_MIN_MOVE_PCT = env_decimal("REPRICE_MIN_MOVE_PCT", "0.00005")  # 0.005%

# Smart adaptive layer.
# The bot keeps a large virtual grid in memory, but places only active orders near live price.
# Example SOL: LOWER_PRICE=80, UPPER_PRICE=120, VIRTUAL_GRID_STEP=0.001.
# Real order price is still rounded by Binance tick size.
USE_SMART_ANALYSIS = env_bool("USE_SMART_ANALYSIS", "true")
VIRTUAL_GRID_STEP = env_decimal("VIRTUAL_GRID_STEP", "0.001")
SIGNAL_CONFIRM_SECONDS = env_float("SIGNAL_CONFIRM_SECONDS", "20")
ANALYSIS_REFRESH_SECONDS = env_float("ANALYSIS_REFRESH_SECONDS", "5")
BIAS_THRESHOLD = env_int("BIAS_THRESHOLD", "15")
STRONG_BIAS_THRESHOLD = env_int("STRONG_BIAS_THRESHOLD", "35")
COUNTER_BIAS_OFFSET_PCT = env_decimal("COUNTER_BIAS_OFFSET_PCT", "0.0015")  # 0.15% farther from price
DISABLE_COUNTER_ON_STRONG_BIAS = env_bool("DISABLE_COUNTER_ON_STRONG_BIAS", "false")
MAX_SPREAD_PCT = env_decimal("MAX_SPREAD_PCT", "0.0015")  # 0.15%; skip if spread is crazy
MAX_FAST_MOVE_PCT = env_decimal("MAX_FAST_MOVE_PCT", "0.012")  # 1.2% fast 5m move => danger/skip

# Main trading logic.
# Net est is the main clean-profit trigger.
TAKE_NET_PROFIT = env_decimal("TAKE_NET_PROFIT", "0.05")
MAX_CYCLE_LOSS = env_decimal("MAX_CYCLE_LOSS", "-0.60")

# Optional fast trigger that follows Binance UI unrealized PnL.
# It is faster for scalping, but less exact than executable Net est.
# 0 disables this trigger. Example: 0.20 means close when Binance UI uPnL >= +0.20 USDT
# AND Net est is not worse than EXCHANGE_TAKE_MIN_NET.
TAKE_EXCHANGE_UPNL = env_decimal("TAKE_EXCHANGE_UPNL", "0.20")
EXCHANGE_TAKE_MIN_NET = env_decimal("EXCHANGE_TAKE_MIN_NET", "-0.05")

# Native TP order on the exchange after entry. This catches fast spikes better than REST polling.
USE_TP_LIMIT_ORDER = env_bool("USE_TP_LIMIT_ORDER", "true")

# More useful tick diagnostics in logs.
DETAILED_TICK_LOG = env_bool("DETAILED_TICK_LOG", "true")

COOLDOWN_SECONDS = env_int("COOLDOWN_SECONDS", "30")
LOSS_COOLDOWN_SECONDS = env_int("LOSS_COOLDOWN_SECONDS", "30")
TOTAL_RUNTIME_SECONDS = env_int("TOTAL_RUNTIME_SECONDS", str(4 * 60 * 60))
CHECK_INTERVAL_SECONDS = env_float("CHECK_INTERVAL_SECONDS", "0.25")
PRINT_INTERVAL_SECONDS = env_float("PRINT_INTERVAL_SECONDS", "2")
TELEGRAM_STATUS_EVERY_SECONDS = env_int("TELEGRAM_STATUS_EVERY_SECONDS", "60")

# Low-latency mode: do not call slow account balance / allOrders on every tick.
# Position + book are enough to make the close decision.
LIVE_WALLET_IN_LOOP = env_bool("LIVE_WALLET_IN_LOOP", "false")

# Network protection
REQUEST_TIMEOUT_SECONDS = env_int("REQUEST_TIMEOUT_SECONDS", "12")
API_RETRY_SLEEP_SECONDS = env_int("API_RETRY_SLEEP_SECONDS", "5")
API_DOWNTIME_NOTIFY_EVERY_SECONDS = env_int("API_DOWNTIME_NOTIFY_EVERY_SECONDS", "120")

# Safety
FORCE_DEMO_ONLY = env_bool("FORCE_DEMO_ONLY", "true")
CLOSE_ON_START = env_bool("CLOSE_ON_START", "true")
CLOSE_ON_EXIT = env_bool("CLOSE_ON_EXIT", "false")  # Railway restart should not auto-close unless you want it

API_KEY = env_str("BINANCE_API_KEY", "")
SECRET_KEY = env_str("BINANCE_SECRET_KEY", "")

TELEGRAM_BOT_TOKEN = env_str("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = env_str("TELEGRAM_CHAT_ID", "")

HEADERS = {"X-MBX-APIKEY": API_KEY}
SESSION = requests.Session()
TIME_OFFSET_MS = 0
_LAST_NETWORK_ALERT_AT = 0.0
_NETWORK_WAS_DOWN = False
_LAST_TELEGRAM_ERROR_AT = 0.0


# ============================================================
# SMALL HELPERS
# ============================================================

def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def dstr(value: Any) -> str:
    return format(Decimal(value), "f")


def fmt4(value: Any) -> str:
    try:
        return f"{Decimal(str(value)):.4f}"
    except Exception:
        return str(value)


def format_duration(seconds: float) -> str:
    seconds_i = int(seconds)
    hours = seconds_i // 3600
    minutes = (seconds_i % 3600) // 60
    secs = seconds_i % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def safe_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def money(value: Any, digits: int = 4) -> str:
    return f"{safe_decimal(value):+.{digits}f}"


def plain_money(value: Any, digits: int = 4) -> str:
    return f"{safe_decimal(value):.{digits}f}"


def side_ua(side: Any) -> str:
    s = str(side).upper()
    if s == "LONG":
        return "🟢 LONG"
    if s == "SHORT":
        return "🔴 SHORT"
    if s == "BOTH":
        return "BOTH"
    return "немає"


def mode_ua(mode: Any) -> str:
    mapping = {
        "RANGE_NEUTRAL": "нейтрально / боковик",
        "LONG_BIAS": "перевага LONG",
        "STRONG_LONG_BIAS": "сильна перевага LONG",
        "SHORT_BIAS": "перевага SHORT",
        "STRONG_SHORT_BIAS": "сильна перевага SHORT",
        "DANGER_SKIP": "небезпечні умови / пропуск",
        "RANGE": "нейтрально",
    }
    return mapping.get(str(mode), str(mode))


def trade_mode_label() -> str:
    return "DEMO" if "demo-fapi" in BASE_URL else "LIVE"


def floor_step(value: Any, step: Any) -> Decimal:
    value_d = Decimal(str(value))
    step_d = Decimal(str(step))
    return (value_d / step_d).to_integral_value(rounding=ROUND_DOWN) * step_d


def round_tick(value: Any, tick: Any) -> Decimal:
    value_d = Decimal(str(value))
    tick_d = Decimal(str(tick))
    return (value_d / tick_d).to_integral_value(rounding=ROUND_HALF_UP) * tick_d


def ceil_step(value: Any, step: Any) -> Decimal:
    value_d = Decimal(str(value))
    step_d = Decimal(str(step))
    return (value_d / step_d).to_integral_value(rounding=ROUND_CEILING) * step_d


def log(message: str, telegram: bool = False) -> None:
    print(message, flush=True)
    if telegram:
        tg_send(message)


def tg_send(text: str) -> None:
    global _LAST_TELEGRAM_ERROR_AT

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text[:3900],
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        requests.post(url, json=payload, timeout=8)
    except Exception as error:
        now = time.monotonic()
        if now - _LAST_TELEGRAM_ERROR_AT > 60:
            print(f"⚠️ Telegram send error: {error}", flush=True)
            _LAST_TELEGRAM_ERROR_AT = now


# ============================================================
# API WITH ANTI-CRASH RETRY
# ============================================================

def _notify_network_down(error: Exception) -> None:
    global _LAST_NETWORK_ALERT_AT, _NETWORK_WAS_DOWN
    now = time.monotonic()

    if now - _LAST_NETWORK_ALERT_AT >= API_DOWNTIME_NOTIFY_EVERY_SECONDS:
        message = (
            "⚠️ Binance API недоступний.\n"
            f"Symbol: {SYMBOL}\n"
            f"Error: {type(error).__name__}: {error}\n"
            f"Чекаю {API_RETRY_SLEEP_SECONDS} сек і пробую знову."
        )
        log(message, telegram=True)
        _LAST_NETWORK_ALERT_AT = now

    _NETWORK_WAS_DOWN = True


def _notify_network_restored() -> None:
    global _NETWORK_WAS_DOWN
    if _NETWORK_WAS_DOWN:
        log("✅ Зв'язок з Binance API відновлено.", telegram=True)
        _NETWORK_WAS_DOWN = False


def request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    while True:
        try:
            response = SESSION.request(method, url, timeout=REQUEST_TIMEOUT_SECONDS, **kwargs)
            _notify_network_restored()
            return response
        except requests.exceptions.RequestException as error:
            _notify_network_down(error)
            time.sleep(API_RETRY_SLEEP_SECONDS)


def public_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
    while True:
        response = request_with_retry("GET", BASE_URL + endpoint, params=params or {})
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as error:
            # Public endpoint HTTP errors are usually temporary on demo; retry.
            _notify_network_down(error)
            time.sleep(API_RETRY_SLEEP_SECONDS)
        except ValueError as error:
            _notify_network_down(error)
            time.sleep(API_RETRY_SLEEP_SECONDS)


def sync_binance_time() -> None:
    global TIME_OFFSET_MS
    data = public_get("/fapi/v1/time")
    server_time = int(data["serverTime"])
    local_time = int(time.time() * 1000)
    TIME_OFFSET_MS = server_time - local_time
    log(f"🕐 Binance time sync: {TIME_OFFSET_MS:+d} ms")


def signed_request(
    method: str,
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    ignore_codes: Optional[set] = None,
    retry_timestamp: bool = True,
) -> Any:
    if params is None:
        params = {}
    if ignore_codes is None:
        ignore_codes = set()

    while True:
        request_params = dict(params)
        request_params["timestamp"] = int(time.time() * 1000) + TIME_OFFSET_MS
        request_params["recvWindow"] = 10000

        query = urlencode(request_params)
        signature = hmac.new(
            SECRET_KEY.encode("utf-8"),
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        url = f"{BASE_URL}{endpoint}?{query}&signature={signature}"
        response = request_with_retry(method, url, headers=HEADERS)

        try:
            data = response.json()
        except Exception:
            data = {"status": response.status_code, "text": response.text}

        if (
            response.status_code >= 400
            and isinstance(data, dict)
            and data.get("code") == -1021
            and retry_timestamp
        ):
            log("⚠️ Timestamp mismatch. Синхронізую час Binance...")
            sync_binance_time()
            return signed_request(method, endpoint, params=params, ignore_codes=ignore_codes, retry_timestamp=False)

        if response.status_code >= 400:
            code = data.get("code") if isinstance(data, dict) else None
            if code in ignore_codes:
                return data

            # API error - not a network crash. Raise so we do not hide real exchange errors.
            raise RuntimeError(f"Binance API error {response.status_code}: {data}")

        return data


# ============================================================
# BINANCE ACCOUNT / MARKET
# ============================================================

def require_env() -> None:
    if FORCE_DEMO_ONLY and "demo-fapi" not in BASE_URL:
        raise RuntimeError("FORCE_DEMO_ONLY=true, але BINANCE_BASE_URL не DEMO. Зупиняюся.")
    if not API_KEY or not SECRET_KEY:
        raise RuntimeError("Не знайдено BINANCE_API_KEY або BINANCE_SECRET_KEY у .env / Railway Variables")


def get_symbol_filters() -> Dict[str, Decimal]:
    info = public_get("/fapi/v1/exchangeInfo")
    symbol_info = None
    for item in info["symbols"]:
        if item["symbol"] == SYMBOL:
            symbol_info = item
            break
    if symbol_info is None:
        raise RuntimeError(f"{SYMBOL} не знайдено в exchangeInfo")

    tick_size = None
    qty_step = None
    market_qty_step = None
    min_qty = Decimal("0")

    for f in symbol_info["filters"]:
        if f["filterType"] == "PRICE_FILTER":
            tick_size = Decimal(f["tickSize"])
        elif f["filterType"] == "LOT_SIZE":
            qty_step = Decimal(f["stepSize"])
            min_qty = Decimal(f["minQty"])
        elif f["filterType"] == "MARKET_LOT_SIZE":
            market_qty_step = Decimal(f["stepSize"])

    if market_qty_step is None:
        market_qty_step = qty_step

    return {
        "tick": tick_size,
        "qty_step": qty_step,
        "market_qty_step": market_qty_step,
        "min_qty": min_qty,
    }


def get_usdt_wallet_balance() -> Decimal:
    data = signed_request("GET", "/fapi/v3/balance")
    for item in data:
        if item["asset"] == "USDT":
            return Decimal(item["balance"])
    return Decimal("0")


def get_book():
    data = public_get("/fapi/v1/ticker/bookTicker", {"symbol": SYMBOL})
    bid = Decimal(data["bidPrice"])
    ask = Decimal(data["askPrice"])
    mid = (bid + ask) / Decimal("2")
    return bid, ask, mid


def get_positions() -> Dict[str, Dict[str, Decimal]]:
    try:
        data = signed_request("GET", "/fapi/v3/positionRisk", {"symbol": SYMBOL})
    except Exception:
        data = signed_request("GET", "/fapi/v2/positionRisk", {"symbol": SYMBOL})

    result = {
        "LONG": {"amount": Decimal("0"), "unrealized": Decimal("0"), "entry_price": Decimal("0")},
        "SHORT": {"amount": Decimal("0"), "unrealized": Decimal("0"), "entry_price": Decimal("0")},
        "BOTH": {"amount": Decimal("0"), "unrealized": Decimal("0"), "entry_price": Decimal("0")},
    }

    for item in data:
        if item.get("symbol") != SYMBOL:
            continue
        side = item.get("positionSide", "BOTH")
        amount = Decimal(item["positionAmt"])
        unrealized = Decimal(item.get("unRealizedProfit", item.get("unrealizedProfit", "0")))
        entry_price = Decimal(item.get("entryPrice", "0"))
        if side in result:
            result[side] = {"amount": amount, "unrealized": unrealized, "entry_price": entry_price}
    return result


def get_taker_fee() -> Decimal:
    try:
        data = signed_request("GET", "/fapi/v1/commissionRate", {"symbol": SYMBOL})
        return Decimal(data["takerCommissionRate"])
    except Exception:
        return Decimal("0.0004")


def ensure_hedge_mode() -> None:
    mode = signed_request("GET", "/fapi/v1/positionSide/dual")
    if mode.get("dualSidePosition") is True:
        log("✅ Hedge Mode вже увімкнено")
        return
    log("⚙️ Вмикаю Hedge Mode...")
    signed_request("POST", "/fapi/v1/positionSide/dual", {"dualSidePosition": "true"})
    log("✅ Hedge Mode увімкнено")


def set_isolated() -> None:
    signed_request(
        "POST",
        "/fapi/v1/marginType",
        {"symbol": SYMBOL, "marginType": "ISOLATED"},
        ignore_codes={-4046},
    )
    log("⚙️ Margin type: ISOLATED")


def set_leverage() -> None:
    result = signed_request("POST", "/fapi/v1/leverage", {"symbol": SYMBOL, "leverage": LEVERAGE})
    log(f"⚙️ Плече: {result.get('leverage', LEVERAGE)}x")


# ============================================================
# ORDERS
# ============================================================

def cancel_all_orders() -> None:
    signed_request("DELETE", "/fapi/v1/allOpenOrders", {"symbol": SYMBOL})


def place_limit_order(side: str, position_side: str, price: Decimal, quantity: Decimal, client_order_id: str) -> Any:
    return signed_request(
        "POST",
        "/fapi/v1/order",
        {
            "symbol": SYMBOL,
            "side": side,
            "positionSide": position_side,
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": dstr(quantity),
            "price": dstr(price),
            "newClientOrderId": client_order_id,
        },
    )


def place_market_close(position_side: str, quantity: Decimal) -> Any:
    if quantity <= 0:
        return None
    if position_side == "LONG":
        side = "SELL"
    elif position_side == "SHORT":
        side = "BUY"
    else:
        raise ValueError("position_side має бути LONG або SHORT")

    return signed_request(
        "POST",
        "/fapi/v1/order",
        {
            "symbol": SYMBOL,
            "side": side,
            "positionSide": position_side,
            "type": "MARKET",
            "quantity": dstr(quantity),
        },
    )


def place_close_limit_order(position_side: str, price: Decimal, quantity: Decimal, client_order_id: str) -> Any:
    if quantity <= 0:
        return None
    if position_side == "LONG":
        side = "SELL"
    elif position_side == "SHORT":
        side = "BUY"
    else:
        raise ValueError("position_side має бути LONG або SHORT")

    return signed_request(
        "POST",
        "/fapi/v1/order",
        {
            "symbol": SYMBOL,
            "side": side,
            "positionSide": position_side,
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": dstr(quantity),
            "price": dstr(price),
            "newClientOrderId": client_order_id,
        },
    )


def fetch_recent_orders() -> Dict[str, Any]:
    data = signed_request("GET", "/fapi/v1/allOrders", {"symbol": SYMBOL, "limit": 1000})
    return {item["clientOrderId"]: item for item in data}


# ============================================================
# CLEANUP / CLOSE
# ============================================================

def has_open_position() -> bool:
    positions = get_positions()
    return any(abs(positions[side]["amount"]) > 0 for side in ["LONG", "SHORT", "BOTH"])


def close_all_positions(filters: Dict[str, Decimal], max_attempts: int = 120, wait_seconds: float = 1.0) -> bool:
    last_error = None

    for attempt in range(1, max_attempts + 1):
        positions = get_positions()
        long_qty = floor_step(abs(positions["LONG"]["amount"]), filters["market_qty_step"])
        short_qty = floor_step(abs(positions["SHORT"]["amount"]), filters["market_qty_step"])
        both_amt = positions["BOTH"]["amount"]
        both_qty = floor_step(abs(both_amt), filters["market_qty_step"])

        if long_qty <= 0 and short_qty <= 0 and both_qty <= 0:
            return True

        if long_qty > 0:
            log(f"🔻 Закриваю LONG MARKET qty {long_qty} (спроба {attempt}/{max_attempts})")
            try:
                place_market_close("LONG", long_qty)
            except RuntimeError as error:
                last_error = error
                log(f"⚠️ LONG MARKET close відхилено: {error}", telegram=True)
            time.sleep(0.3)

        if short_qty > 0:
            log(f"🔻 Закриваю SHORT MARKET qty {short_qty} (спроба {attempt}/{max_attempts})")
            try:
                place_market_close("SHORT", short_qty)
            except RuntimeError as error:
                last_error = error
                log(f"⚠️ SHORT MARKET close відхилено: {error}", telegram=True)
            time.sleep(0.3)

        if both_amt != 0 and both_qty > 0:
            side = "SELL" if both_amt > 0 else "BUY"
            log(f"🔻 Закриваю BOTH MARKET {side} qty {both_qty} (спроба {attempt}/{max_attempts})")
            try:
                signed_request(
                    "POST",
                    "/fapi/v1/order",
                    {"symbol": SYMBOL, "side": side, "type": "MARKET", "quantity": dstr(both_qty), "reduceOnly": "true"},
                )
            except RuntimeError as error:
                last_error = error
                log(f"⚠️ BOTH MARKET close відхилено: {error}", telegram=True)

        time.sleep(wait_seconds)

    raise RuntimeError(f"Не вдалося закрити позиції після {max_attempts} спроб. Остання помилка: {last_error}")


def cleanup(filters: Dict[str, Decimal], close_positions: bool = True) -> None:
    try:
        cancel_all_orders()
    except Exception as error:
        log(f"⚠️ Не зміг скасувати всі ордери: {error}", telegram=True)

    time.sleep(0.5)

    if close_positions:
        try:
            close_all_positions(filters)
        except Exception as error:
            log(f"⚠️ Не зміг закрити позиції: {error}", telegram=True)

    time.sleep(1)



# ============================================================
# SMART MARKET ANALYZER
# ============================================================

def get_klines(interval: str, limit: int = 80) -> List[List[Any]]:
    return public_get("/fapi/v1/klines", {"symbol": SYMBOL, "interval": interval, "limit": limit})


def candle_close(kline: List[Any]) -> Decimal:
    return Decimal(str(kline[4]))


def candle_high(kline: List[Any]) -> Decimal:
    return Decimal(str(kline[2]))


def candle_low(kline: List[Any]) -> Decimal:
    return Decimal(str(kline[3]))


def candle_volume(kline: List[Any]) -> Decimal:
    return Decimal(str(kline[5]))


def ema_decimal(values: List[Decimal], period: int) -> Decimal:
    if not values:
        return Decimal("0")
    if len(values) < period:
        return values[-1]
    k = Decimal("2") / (Decimal(period) + Decimal("1"))
    ema = sum(values[:period]) / Decimal(period)
    for value in values[period:]:
        ema = value * k + ema * (Decimal("1") - k)
    return ema


def rsi_decimal(values: List[Decimal], period: int = 14) -> Decimal:
    if len(values) <= period:
        return Decimal("50")
    gains = Decimal("0")
    losses = Decimal("0")
    recent = values[-(period + 1):]
    for prev, cur in zip(recent, recent[1:]):
        diff = cur - prev
        if diff >= 0:
            gains += diff
        else:
            losses += abs(diff)
    if losses == 0:
        return Decimal("100")
    if gains == 0:
        return Decimal("0")
    rs = gains / losses
    return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))


def atr_pct_decimal(klines: List[List[Any]], period: int = 14) -> Decimal:
    if len(klines) < period + 1:
        return Decimal("0")
    trs: List[Decimal] = []
    prev_close = candle_close(klines[-period - 1])
    for k in klines[-period:]:
        high = candle_high(k)
        low = candle_low(k)
        tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
        trs.append(tr)
        prev_close = candle_close(k)
    close = candle_close(klines[-1])
    if close <= 0:
        return Decimal("0")
    return (sum(trs) / Decimal(len(trs))) / close


def pct_change(values: List[Decimal], lookback: int) -> Decimal:
    if len(values) <= lookback or values[-lookback - 1] <= 0:
        return Decimal("0")
    return (values[-1] - values[-lookback - 1]) / values[-lookback - 1]


def timeframe_signal(interval: str, weight: int) -> Dict[str, Any]:
    kl = get_klines(interval, 80)
    closes = [candle_close(k) for k in kl]
    if len(closes) < 25:
        return {"interval": interval, "score": 0, "text": "no_data", "rsi": Decimal("50"), "atr_pct": Decimal("0")}

    ema9 = ema_decimal(closes, 9)
    ema21 = ema_decimal(closes, 21)
    ema50 = ema_decimal(closes, 50)
    rsi = rsi_decimal(closes, 14)
    change3 = pct_change(closes, 3)
    change10 = pct_change(closes, 10)
    atrp = atr_pct_decimal(kl, 14)

    score = 0
    # EMA structure
    if closes[-1] > ema9 > ema21:
        score += 2 * weight
    elif closes[-1] < ema9 < ema21:
        score -= 2 * weight
    elif ema9 > ema21:
        score += 1 * weight
    elif ema9 < ema21:
        score -= 1 * weight

    # Higher timeframe structure
    if ema21 > ema50:
        score += 1 * weight
    elif ema21 < ema50:
        score -= 1 * weight

    # Momentum, not too sensitive.
    if change3 > Decimal("0.001"):
        score += 1 * weight
    elif change3 < Decimal("-0.001"):
        score -= 1 * weight
    if change10 > Decimal("0.002"):
        score += 1 * weight
    elif change10 < Decimal("-0.002"):
        score -= 1 * weight

    # RSI supports direction, but extremes reduce confidence because reversal risk grows.
    if Decimal("55") <= rsi <= Decimal("72"):
        score += 1 * weight
    elif Decimal("28") <= rsi <= Decimal("45"):
        score -= 1 * weight
    elif rsi > Decimal("78"):
        score -= 1 * weight
    elif rsi < Decimal("22"):
        score += 1 * weight

    if score > 0:
        text = "up"
    elif score < 0:
        text = "down"
    else:
        text = "flat"

    return {
        "interval": interval,
        "score": int(score),
        "text": text,
        "close": closes[-1],
        "ema9": ema9,
        "ema21": ema21,
        "ema50": ema50,
        "rsi": rsi,
        "change3": change3,
        "change10": change10,
        "atr_pct": atrp,
    }


def analyze_market(filters: Optional[Dict[str, Decimal]] = None) -> Dict[str, Any]:
    if not USE_SMART_ANALYSIS:
        return {"mode": "RANGE", "score": 0, "bias": "NEUTRAL", "danger": False, "reason": "smart_analysis_off", "details": []}

    bid, ask, mid = get_book()
    spread_pct = ((ask - bid) / mid) if mid > 0 else Decimal("0")

    # We use supported Binance intervals. 10m is represented by 1m/5m + 15m context to avoid unsupported kline intervals.
    weights = {"1m": 1, "5m": 2, "15m": 3, "1h": 4}
    details = []
    total_score = 0
    max_fast_move = Decimal("0")
    max_atr = Decimal("0")

    for interval, weight in weights.items():
        try:
            sig = timeframe_signal(interval, weight)
            details.append(sig)
            total_score += int(sig.get("score", 0))
            max_fast_move = max(max_fast_move, abs(Decimal(str(sig.get("change3", "0")))))
            max_atr = max(max_atr, Decimal(str(sig.get("atr_pct", "0"))))
        except Exception as error:
            details.append({"interval": interval, "score": 0, "text": f"error:{type(error).__name__}", "rsi": Decimal("50"), "atr_pct": Decimal("0")})

    danger_reasons = []
    if mid <= LOWER_PRICE or mid >= UPPER_PRICE:
        danger_reasons.append("outside_range")
    if spread_pct > MAX_SPREAD_PCT:
        danger_reasons.append(f"spread>{(MAX_SPREAD_PCT*Decimal('100')):.3f}%")
    if max_fast_move > MAX_FAST_MOVE_PCT:
        danger_reasons.append(f"fast_move>{(MAX_FAST_MOVE_PCT*Decimal('100')):.2f}%")

    if danger_reasons:
        mode = "DANGER_SKIP"
        bias = "SKIP"
    elif total_score >= STRONG_BIAS_THRESHOLD:
        mode = "STRONG_LONG_BIAS"
        bias = "LONG"
    elif total_score >= BIAS_THRESHOLD:
        mode = "LONG_BIAS"
        bias = "LONG"
    elif total_score <= -STRONG_BIAS_THRESHOLD:
        mode = "STRONG_SHORT_BIAS"
        bias = "SHORT"
    elif total_score <= -BIAS_THRESHOLD:
        mode = "SHORT_BIAS"
        bias = "SHORT"
    else:
        mode = "RANGE_NEUTRAL"
        bias = "NEUTRAL"

    reason_parts = [f"score={total_score}", f"spread={(spread_pct*Decimal('100')):.4f}%"]
    if danger_reasons:
        reason_parts.append("danger=" + ",".join(danger_reasons))
    for d in details:
        rsi = d.get("rsi", Decimal("50"))
        try:
            rsi_text = f"{Decimal(str(rsi)):.1f}"
        except Exception:
            rsi_text = str(rsi)
        reason_parts.append(f"{d.get('interval')}:{d.get('text')}({d.get('score')},rsi={rsi_text})")

    return {
        "mode": mode,
        "bias": bias,
        "score": total_score,
        "danger": bool(danger_reasons),
        "danger_reasons": danger_reasons,
        "reason": " | ".join(reason_parts),
        "details": details,
        "bid": bid,
        "ask": ask,
        "mid": mid,
        "spread_pct": spread_pct,
        "max_atr_pct": max_atr,
    }


def snap_virtual_price(value: Decimal, side: str, filters: Dict[str, Decimal]) -> Decimal:
    # Virtual grid step is a planning grid. Binance tick size is the final hard rounding.
    virtual_step = max(VIRTUAL_GRID_STEP, filters["tick"])
    if side == "BUY":
        return floor_step(floor_step(value, virtual_step), filters["tick"])
    return ceil_step(ceil_step(value, virtual_step), filters["tick"])


def analysis_short_text(analysis: Dict[str, Any]) -> str:
    return f"{analysis.get('mode')} | score {analysis.get('score')} | {analysis.get('reason')}"

# ============================================================
# GRID CYCLE
# ============================================================

class OneShotNetGridCycle:
    def __init__(self, cycle_number: int, filters: Dict[str, Decimal], taker_fee: Decimal):
        self.cycle_number = cycle_number
        self.filters = filters
        self.taker_fee = taker_fee
        self.orders: Dict[str, Dict[str, Any]] = {}
        self.nonce = 0
        self.session_tag = datetime.now().strftime("%H%M%S")
        self.levels = self.build_levels()
        self.start_wallet = get_usdt_wallet_balance()
        self.notional_per_cell = ORDER_NOTIONAL_USDT
        self.entry_filled = False
        self.active_side = None
        self.entry_count = 0
        self.tp_order_placed = False
        self.best_net = Decimal('-999999')
        self.best_exchange_upnl = Decimal('-999999')
        self.last_reprice_at = 0.0
        self.entry_revision = 0
        self.current_long_entry_price = Decimal('0')
        self.current_short_entry_price = Decimal('0')
        self.last_analysis: Dict[str, Any] = {"mode": "RANGE_NEUTRAL", "bias": "NEUTRAL", "score": 0, "reason": "init"}
        self.last_analysis_at = 0.0
        self.last_signal_mode = None
        self.last_signal_since = 0.0

    def build_levels(self):
        step = (UPPER_PRICE - LOWER_PRICE) / Decimal(GRID_COUNT)
        levels = []
        for i in range(GRID_COUNT + 1):
            price = round_tick(LOWER_PRICE + step * Decimal(i), self.filters["tick"])
            if price not in levels:
                levels.append(price)
        levels.sort()
        return levels

    def client_id(self, role: str, side_type: str, level_index: int) -> str:
        self.nonce += 1
        return f"G{self.cycle_number}{self.session_tag}{role}{side_type[0]}{level_index}{self.nonce}"

    def qty_for_price(self, price: Decimal) -> Decimal:
        return floor_step(self.notional_per_cell / price, self.filters["qty_step"])

    def register_order(self, data: Dict[str, Any], role: str, side_type: str, level_index: int, price: Decimal, quantity: Decimal) -> None:
        cid = data["clientOrderId"]
        self.orders[cid] = {
            "order_id": data["orderId"],
            "client_id": cid,
            "role": role,
            "side_type": side_type,
            "level_index": level_index,
            "price": Decimal(str(price)),
            "quantity": Decimal(str(quantity)),
            "status": "NEW",
            "processed": False,
        }

    def place_long_entry(self, level_index: int, price: Decimal) -> bool:
        qty = self.qty_for_price(price)
        if qty < self.filters["min_qty"]:
            return False
        cid = self.client_id("E", "LONG", level_index)
        data = place_limit_order("BUY", "LONG", price, qty, cid)
        self.register_order(data, "ENTRY", "LONG", level_index, price, qty)
        return True

    def place_short_entry(self, level_index: int, price: Decimal) -> bool:
        qty = self.qty_for_price(price)
        if qty < self.filters["min_qty"]:
            return False
        cid = self.client_id("E", "SHORT", level_index)
        data = place_limit_order("SELL", "SHORT", price, qty, cid)
        self.register_order(data, "ENTRY", "SHORT", level_index, price, qty)
        return True

    def get_market_analysis(self, force: bool = False) -> Dict[str, Any]:
        now = time.monotonic()
        if force or not self.last_analysis or now - self.last_analysis_at >= ANALYSIS_REFRESH_SECONDS:
            self.last_analysis = analyze_market(self.filters)
            self.last_analysis_at = now
        return self.last_analysis

    def signal_is_confirmed(self, analysis: Dict[str, Any]) -> bool:
        mode = str(analysis.get("mode", "RANGE_NEUTRAL"))
        now = time.monotonic()
        if mode != self.last_signal_mode:
            self.last_signal_mode = mode
            self.last_signal_since = now
            return SIGNAL_CONFIRM_SECONDS <= 0
        return (now - self.last_signal_since) >= SIGNAL_CONFIRM_SECONDS

    def wait_for_stable_signal(self) -> Dict[str, Any]:
        if not USE_SMART_ANALYSIS or SIGNAL_CONFIRM_SECONDS <= 0:
            return self.get_market_analysis(force=True)

        log(f"🧠 Аналізую ринок {SIGNAL_CONFIRM_SECONDS:.0f} сек перед входом...")
        last_notify = 0.0
        while True:
            analysis = self.get_market_analysis(force=True)
            confirmed = self.signal_is_confirmed(analysis)
            now = time.monotonic()
            if now - last_notify >= 5:
                log(f"🧠 Signal check: {analysis_short_text(analysis)}")
                last_notify = now
            if confirmed:
                return analysis
            time.sleep(min(ANALYSIS_REFRESH_SECONDS, 2.0))

    def compute_offset_entry_prices(self, analysis: Optional[Dict[str, Any]] = None):
        bid, ask, mid = get_book()
        if analysis is None:
            analysis = self.get_market_analysis(force=False)

        bias = str(analysis.get("bias", "NEUTRAL"))
        mode = str(analysis.get("mode", "RANGE_NEUTRAL"))

        if analysis.get("danger") or bias == "SKIP":
            return bid, ask, mid, Decimal("0"), Decimal("0"), False, False, analysis

        # Neutral: both orders close. Bias: favored side close, counter side farther.
        long_offset = ENTRY_OFFSET_PCT
        short_offset = ENTRY_OFFSET_PCT
        place_long = True
        place_short = True

        if bias == "LONG":
            long_offset = ENTRY_OFFSET_PCT
            short_offset = COUNTER_BIAS_OFFSET_PCT
            if mode == "STRONG_LONG_BIAS" and DISABLE_COUNTER_ON_STRONG_BIAS:
                place_short = False
        elif bias == "SHORT":
            short_offset = ENTRY_OFFSET_PCT
            long_offset = COUNTER_BIAS_OFFSET_PCT
            if mode == "STRONG_SHORT_BIAS" and DISABLE_COUNTER_ON_STRONG_BIAS:
                place_long = False

        # Entry plan from live book, snapped to virtual grid and then Binance tick size.
        long_raw = bid * (Decimal("1") - long_offset)
        short_raw = ask * (Decimal("1") + short_offset)
        long_price = snap_virtual_price(long_raw, "BUY", self.filters)
        short_price = snap_virtual_price(short_raw, "SELL", self.filters)

        # Extra protection after rounding: never cross the book accidentally.
        if long_price >= ask:
            long_price = floor_step(ask - self.filters["tick"], self.filters["tick"])
        if short_price <= bid:
            short_price = ceil_step(bid + self.filters["tick"], self.filters["tick"])

        return bid, ask, mid, long_price, short_price, place_long, place_short, analysis

    def place_offset_entry_pair(self, reason: str = "START", notify: bool = False) -> bool:
        analysis = self.get_market_analysis(force=True)
        bid, ask, mid, long_price, short_price, place_long, place_short, analysis = self.compute_offset_entry_prices(analysis)

        if mid <= LOWER_PRICE or mid >= UPPER_PRICE:
            log(f"🟡 Ціна {mid} поза діапазоном {LOWER_PRICE}-{UPPER_PRICE}")
            return False

        if analysis.get("danger") or analysis.get("bias") == "SKIP":
            log(f"🟡 SKIP entry: {analysis_short_text(analysis)}", telegram=notify)
            self.last_reprice_at = time.monotonic()
            return False

        if (place_long and long_price <= 0) or (place_short and short_price <= 0):
            log("🟡 Не вдалося розрахувати коректні entry-ціни")
            return False

        self.entry_revision += 1
        self.current_long_entry_price = long_price if place_long else Decimal("0")
        self.current_short_entry_price = short_price if place_short else Decimal("0")
        self.last_reprice_at = time.monotonic()

        placed_long = 0
        placed_short = 0
        try:
            if place_long:
                placed_long = 1 if self.place_long_entry(self.entry_revision * 10, long_price) else 0
                time.sleep(0.02)
            if place_short:
                placed_short = 1 if self.place_short_entry(self.entry_revision * 10 + 1, short_price) else 0
        except Exception as error:
            log(f"⚠️ Не зміг виставити smart adaptive entry ордери: {error}", telegram=True)
            return False

        max_active_orders = Decimal(placed_long + placed_short)
        max_active_notional = ORDER_NOTIONAL_USDT * max_active_orders
        max_active_margin = max_active_notional / Decimal(LEVERAGE) if LEVERAGE else Decimal("0")

        msg = (
            f"🔁 Smart adaptive entry {reason} #{self.entry_revision}\n"
            f"{SYMBOL} bid/ask/mid: {bid} / {ask} / {mid}\n"
            f"Mode: {analysis.get('mode')} | Bias: {analysis.get('bias')} | Score: {analysis.get('score')}\n"
            f"Reason: {analysis.get('reason')}\n"
            f"Virtual range/grid: {LOWER_PRICE}-{UPPER_PRICE} step {VIRTUAL_GRID_STEP}\n"
            f"BUY LONG: {long_price if place_long else 'disabled'}\n"
            f"SELL SHORT: {short_price if place_short else 'disabled'}\n"
            f"Near offset: {(ENTRY_OFFSET_PCT * Decimal('100')):.4f}% | Counter offset: {(COUNTER_BIAS_OFFSET_PCT * Decimal('100')):.4f}%\n"
            f"Reprice: {REPRICE_ENTRY_SECONDS}s | Orders: LONG {placed_long} + SHORT {placed_short}\n"
            f"Notional per entry: {ORDER_NOTIONAL_USDT} USDT | Max active margin ≈ {max_active_margin:.2f} USDT"
        )
        log(msg, telegram=notify)
        return placed_long + placed_short > 0

    def start(self) -> bool:
        analysis = self.wait_for_stable_signal()
        bid, ask, mid, long_price, short_price, place_long, place_short, analysis = self.compute_offset_entry_prices(analysis)
        if mid <= LOWER_PRICE or mid >= UPPER_PRICE:
            log(f"🟡 Ціна {mid} поза діапазоном {LOWER_PRICE}-{UPPER_PRICE}")
            return False
        if analysis.get("danger") or analysis.get("bias") == "SKIP":
            log(f"🟡 Вхід пропущено: {analysis_short_text(analysis)}")
            return False

        active_orders = Decimal((1 if place_long else 0) + (1 if place_short else 0))
        max_active_notional = ORDER_NOTIONAL_USDT * active_orders
        max_active_margin = max_active_notional / Decimal(LEVERAGE) if LEVERAGE else Decimal("0")

        header = (
            f"🟢 ЦИКЛ #{self.cycle_number}: ПІДГОТОВКА ВХОДУ\n"
            f"Пара: {SYMBOL} | Режим: {trade_mode_label()}\n"
            f"Ринок: {mode_ua(analysis.get('mode'))} | score {analysis.get('score')}\n"
            f"Ціна зараз: bid {bid} / ask {ask}\n"
            f"План ордерів:\n"
            f"• LONG: {long_price if place_long else 'вимкнено'}\n"
            f"• SHORT: {short_price if place_short else 'вимкнено'}\n"
            f"Розмір входу: {ORDER_NOTIONAL_USDT} USDT номінал ≈ {max_active_margin:.2f} USDT маржі при {LEVERAGE}x\n"
            f"Цілі: TP Net +{TAKE_NET_PROFIT} USDT | SL {MAX_CYCLE_LOSS} USDT\n"
            f"TP-ордер на біржі: {'так' if USE_TP_LIMIT_ORDER else 'ні'}"
        )
        log("\n" + "=" * 68)
        log(header, telegram=True)
        log("=" * 68)

        ok = self.place_offset_entry_pair(reason="START", notify=False)
        log(f"💵 Wallet на старті циклу: {self.start_wallet:.4f} USDT")
        return ok

    def should_reprice_entries(self) -> bool:
        if self.entry_filled:
            return False
        if REPRICE_ENTRY_SECONDS <= 0:
            return False
        if time.monotonic() - self.last_reprice_at < REPRICE_ENTRY_SECONDS:
            return False

        try:
            analysis = self.get_market_analysis(force=True)
            if not self.signal_is_confirmed(analysis):
                return False
            bid, ask, mid, new_long, new_short, place_long, place_short, analysis = self.compute_offset_entry_prices(analysis)
        except Exception:
            return True

        if analysis.get("danger") or analysis.get("bias") == "SKIP":
            return True

        # If current entry prices are empty but that side should be active, reprice.
        if place_long and self.current_long_entry_price <= 0:
            return True
        if place_short and self.current_short_entry_price <= 0:
            return True

        moves = []
        if place_long and self.current_long_entry_price > 0:
            moves.append(abs(new_long - self.current_long_entry_price) / self.current_long_entry_price)
        if place_short and self.current_short_entry_price > 0:
            moves.append(abs(new_short - self.current_short_entry_price) / self.current_short_entry_price)
        if not moves:
            return True
        return max(moves) >= REPRICE_MIN_MOVE_PCT

    def reprice_entry_orders_if_needed(self, stats: Optional[Dict[str, Decimal]] = None) -> None:
        """While flat, cancel stale entry orders and recreate them around live price."""
        if self.entry_filled:
            return

        # If there is already a live position, do not reprice; detect it instead.
        if stats and stats.get("position_amount", Decimal("0")) > 0:
            self.mark_entry_from_stats(stats)
            return

        if not self.should_reprice_entries():
            return

        try:
            cancel_all_orders()
            time.sleep(0.05)
        except Exception as error:
            log(f"⚠️ Не зміг скасувати старі entry перед reprice: {error}", telegram=True)
            return

        # Check again after cancel: if an order got filled during cancellation, do not place new entries.
        fresh_stats = self.estimated_net_pnl()
        if fresh_stats.get("position_amount", Decimal("0")) > 0:
            self.mark_entry_from_stats(fresh_stats)
            return

        self.place_offset_entry_pair(reason="REPRICE", notify=False)

    def calc_tp_limit_price(self, side_type: str, entry_price: Decimal, quantity: Decimal) -> Decimal:
        """Return close-limit price that should produce TAKE_NET_PROFIT after estimated taker fees.

        It is only an estimate. Real realized PnL depends on actual fill fee and slippage.
        """
        qty = Decimal(str(quantity))
        entry = Decimal(str(entry_price))
        fee = self.taker_fee
        target = TAKE_NET_PROFIT

        if qty <= 0 or entry <= 0:
            return Decimal('0')

        if side_type == "LONG":
            # net = (close-entry)*qty - entry*qty*fee - close*qty*fee
            raw = (target + entry * qty * (Decimal('1') + fee)) / (qty * (Decimal('1') - fee))
            return ceil_step(raw, self.filters["tick"])

        if side_type == "SHORT":
            # net = (entry-close)*qty - entry*qty*fee - close*qty*fee
            raw = (entry * qty * (Decimal('1') - fee) - target) / (qty * (Decimal('1') + fee))
            return floor_step(raw, self.filters["tick"])

        return Decimal('0')

    def place_native_tp_limit(self, stats: Dict[str, Decimal]) -> None:
        if not USE_TP_LIMIT_ORDER or self.tp_order_placed:
            return

        side_type = str(stats.get("active_side", "NONE"))
        qty = floor_step(stats.get("position_amount", Decimal('0')), self.filters["qty_step"])
        entry_price = stats.get("active_entry_price", Decimal('0'))

        if side_type not in {"LONG", "SHORT"} or qty <= 0 or entry_price <= 0:
            return

        tp_price = self.calc_tp_limit_price(side_type, entry_price, qty)
        if tp_price <= 0:
            return

        cid = self.client_id("T", side_type, 99)
        try:
            place_close_limit_order(side_type, tp_price, qty, cid)
            self.tp_order_placed = True
            log(
                f"🎯 TP-ОРДЕР ВИСТАВЛЕНО\n"
                f"Пара: {SYMBOL}\n"
                f"Позиція: {side_ua(side_type)}\n"
                f"Ціна TP: {tp_price}\n"
                f"Кількість: {qty}\n"
                f"Ціль: приблизно +{TAKE_NET_PROFIT} USDT чистими",
                telegram=True,
            )
        except Exception as error:
            log(f"⚠️ Не зміг поставити TP LIMIT: {error}", telegram=True)

    def update_fills(self) -> None:
        exchange_orders = fetch_recent_orders()
        for cid, local_order in list(self.orders.items()):
            if local_order["processed"]:
                continue
            exchange_order = exchange_orders.get(cid)
            if not exchange_order:
                continue
            status = exchange_order.get("status")
            local_order["status"] = status
            if status != "FILLED":
                continue

            local_order["processed"] = True
            role = local_order["role"]
            side_type = local_order["side_type"]
            price = local_order["price"]
            qty = local_order["quantity"]

            if role == "ENTRY":
                self.entry_count += 1
                if self.entry_filled:
                    log(f"⚠️ ДОДАТКОВИЙ {side_type} ENTRY filled @ {price} qty {qty}. Закриємо по Net est target/stop.", telegram=True)
                    cancel_all_orders()
                    time.sleep(0.2)
                    continue

                self.entry_filled = True
                self.active_side = side_type
                notional = price * qty
                margin_est = notional / Decimal(LEVERAGE) if LEVERAGE else Decimal("0")
                log(
                    f"✅ ПОЗИЦІЮ ВІДКРИТО\n"
                    f"Пара: {SYMBOL}\n"
                    f"Напрямок: {side_ua(side_type)}\n"
                    f"Вхід: {price}\n"
                    f"Кількість: {qty}\n"
                    f"Номінал: ≈ {plain_money(notional, 2)} USDT\n"
                    f"Маржа: ≈ {plain_money(margin_est, 2)} USDT при {LEVERAGE}x",
                    telegram=True,
                )

                # One-shot: after first entry, remove the opposite entry.
                # No TP order. Bot exits only by Net est target/stop.
                cancel_all_orders()
                time.sleep(0.2)

    def mark_entry_from_stats(self, stats: Dict[str, Decimal]) -> None:
        """Detect entry via live position instead of slow allOrders polling."""
        if self.entry_filled:
            return
        if stats.get("position_amount", Decimal("0")) <= 0:
            return

        self.entry_filled = True
        self.active_side = str(stats.get("active_side", "UNKNOWN"))
        price = stats.get("active_entry_price", Decimal("0"))
        qty = stats.get("position_amount", Decimal("0"))
        notional = price * qty
        margin_est = notional / Decimal(LEVERAGE) if LEVERAGE else Decimal("0")
        log(
            f"✅ ПОЗИЦІЮ ВІДКРИТО\n"
            f"Пара: {SYMBOL}\n"
            f"Напрямок: {side_ua(self.active_side)}\n"
            f"Вхід: {price}\n"
            f"Кількість: {qty}\n"
            f"Номінал: ≈ {plain_money(notional, 2)} USDT\n"
            f"Маржа: ≈ {plain_money(margin_est, 2)} USDT при {LEVERAGE}x\n"
            f"TP Net: +{TAKE_NET_PROFIT} USDT | SL: {MAX_CYCLE_LOSS} USDT",
            telegram=True,
        )

        # One-shot: after first live position appears, remove opposite entry as fast as possible.
        try:
            cancel_all_orders()
        except Exception as error:
            log(f"⚠️ Не зміг швидко скасувати протилежний entry: {error}", telegram=True)

        # Put a native TP limit directly on Binance so a fast spike can be caught by the exchange,
        # not only by our REST polling loop.
        self.place_native_tp_limit(stats)

    def estimated_net_pnl(self) -> Dict[str, Decimal]:
        if LIVE_WALLET_IN_LOOP:
            wallet_now = get_usdt_wallet_balance()
            wallet_change = wallet_now - self.start_wallet
        else:
            # Fast mode: balance endpoint is slow and not needed for close decisions.
            wallet_now = self.start_wallet
            wallet_change = Decimal("0")

        positions = get_positions()
        bid, ask, mid = get_book()

        executable_unrealized = Decimal("0")
        exit_notional = Decimal("0")
        entry_notional = Decimal("0")

        # IMPORTANT:
        # Do NOT add wallet_change to Net est while an isolated position is open.
        # In isolated margin Binance may move margin from the wallet to the position.
        # That locked margin is not a real trading loss and must not trigger/avoid exits.

        # LONG closes by SELL at bid.
        long_amount = abs(positions["LONG"]["amount"])
        long_entry = positions["LONG"]["entry_price"]
        if long_amount > 0:
            executable_unrealized += ((bid - long_entry) * long_amount) if long_entry > 0 else positions["LONG"]["unrealized"]
            exit_notional += long_amount * bid
            if long_entry > 0:
                entry_notional += long_amount * long_entry

        # SHORT closes by BUY at ask.
        short_amount = abs(positions["SHORT"]["amount"])
        short_entry = positions["SHORT"]["entry_price"]
        if short_amount > 0:
            executable_unrealized += ((short_entry - ask) * short_amount) if short_entry > 0 else positions["SHORT"]["unrealized"]
            exit_notional += short_amount * ask
            if short_entry > 0:
                entry_notional += short_amount * short_entry

        both_amount = positions["BOTH"]["amount"]
        both_entry = positions["BOTH"]["entry_price"]
        if both_amount > 0:
            qty = abs(both_amount)
            executable_unrealized += ((bid - both_entry) * qty) if both_entry > 0 else positions["BOTH"]["unrealized"]
            exit_notional += qty * bid
            if both_entry > 0:
                entry_notional += qty * both_entry
        elif both_amount < 0:
            qty = abs(both_amount)
            executable_unrealized += ((both_entry - ask) * qty) if both_entry > 0 else positions["BOTH"]["unrealized"]
            exit_notional += qty * ask
            if both_entry > 0:
                entry_notional += qty * both_entry

        entry_fee_est = entry_notional * self.taker_fee
        exit_fee_est = exit_notional * self.taker_fee

        # Net est is now the estimated clean result if we close right now:
        # executable PnL minus estimated entry and exit commissions.
        net = executable_unrealized - entry_fee_est - exit_fee_est
        exchange_unrealized = sum(item["unrealized"] for item in positions.values())

        active_side = "NONE"
        active_entry_price = Decimal("0")
        position_amount = Decimal("0")
        close_price = Decimal("0")
        if long_amount > 0:
            active_side = "LONG"
            active_entry_price = long_entry
            position_amount = long_amount
            close_price = bid
        elif short_amount > 0:
            active_side = "SHORT"
            active_entry_price = short_entry
            position_amount = short_amount
            close_price = ask
        elif both_amount != 0:
            active_side = "LONG" if both_amount > 0 else "SHORT"
            active_entry_price = both_entry
            position_amount = abs(both_amount)
            close_price = bid if both_amount > 0 else ask

        return {
            "wallet": wallet_now,
            "wallet_change": wallet_change,
            "unrealized": executable_unrealized,
            "exchange_unrealized": exchange_unrealized,
            "entry_fee_est": entry_fee_est,
            "exit_fee_est": exit_fee_est,
            "net": net,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread": ask - bid,
            "close_price": close_price,
            "active_side": active_side,
            "active_entry_price": active_entry_price,
            "position_amount": position_amount,
        }


def finish_cycle_already_closed(cycle: OneShotNetGridCycle, started_at: float, reason: str = "TP LIMIT / POSITION CLOSED") -> str:
    try:
        cancel_all_orders()
    except Exception as error:
        log(f"⚠️ Не зміг скасувати залишкові ордери після закриття: {error}", telegram=True)

    final_wallet = get_usdt_wallet_balance()
    actual = final_wallet - cycle.start_wallet
    result = "TARGET" if actual >= 0 else "STOP"
    symbol = "✅" if actual >= 0 else "❌"
    msg = (
        f"{symbol} ПОЗИЦІЮ ЗАКРИТО\n"
        f"Причина: {reason}\n"
        f"Пара: {SYMBOL}\n"
        f"Результат циклу: {money(actual)} USDT\n"
        f"Найкращий Net est: {money(cycle.best_net)} USDT\n"
        f"Найкращий Binance PnL: {money(cycle.best_exchange_upnl)} USDT\n"
        f"Час у позиції/циклі: {format_duration(time.monotonic() - started_at)}"
    )
    log(msg, telegram=True)
    return result

def close_cycle(cycle: OneShotNetGridCycle, filters: Dict[str, Decimal], reason: str, stats: Dict[str, Decimal], started_at: float, is_stop: bool) -> str:
    # LOW LATENCY IMPORTANT:
    # First close the live position. Telegram and detailed messages go AFTER close.
    # If we send Telegram before market close, a fast spike can disappear while we are notifying.
    log(f"\n{reason} | Net est: {stats['net']:+.4f} USDT — ЗАКРИВАЮ НЕГАЙНО")

    close_error = None
    try:
        close_all_positions(filters, max_attempts=20, wait_seconds=0.15)
    except Exception as error:
        close_error = error
        log(f"⚠️ Перша спроба закриття дала помилку: {error}")

    try:
        cancel_all_orders()
    except Exception as error:
        log(f"⚠️ Не зміг скасувати ордери після close: {error}")

    # Safety verification/retry.
    try:
        close_all_positions(filters, max_attempts=20, wait_seconds=0.15)
    except Exception as error:
        close_error = error
        log(f"⚠️ Повторне закриття дало помилку: {error}")

    time.sleep(0.4)

    final_wallet = get_usdt_wallet_balance()
    actual = final_wallet - cycle.start_wallet
    symbol = "❌" if is_stop or actual < 0 else "✅"
    verdict = "СТОП" if is_stop else "ТЕЙК"

    msg = (
        f"{symbol} ПОЗИЦІЮ ЗАКРИТО — {verdict}\n"
        f"Пара: {SYMBOL}\n"
        f"Напрямок: {side_ua(stats['active_side'])}\n"
        f"Вхід: {stats['active_entry_price']}\n"
        f"Ціна закриття/розрахунку: {stats.get('close_price', Decimal('0'))}\n"
        f"Кількість: {stats['position_amount']}\n"
        f"Результат фактичний: {money(actual)} USDT\n"
        f"Net est при тригері: {money(stats['net'])} USDT\n"
        f"Binance PnL при тригері: {money(stats['exchange_unrealized'])} USDT\n"
        f"Комісії оцінка: {plain_money(stats['entry_fee_est'], 4)} + {plain_money(stats['exit_fee_est'], 4)} USDT\n"
        f"Best Net / Best PnL: {money(cycle.best_net)} / {money(cycle.best_exchange_upnl)} USDT\n"
        f"Час у циклі: {format_duration(time.monotonic() - started_at)}\n"
        f"Причина: {reason}"
    )
    if close_error:
        msg += f"\n⚠️ Попередження по закриттю: {close_error}"
    log(msg, telegram=True)
    return "STOP" if is_stop else "TARGET"

def run_cycle(cycle_number: int, filters: Dict[str, Decimal], taker_fee: Decimal, session_end: float) -> str:
    # We close old positions only at the start of a new bot session if CLOSE_ON_START=true.
    cycle = OneShotNetGridCycle(cycle_number, filters, taker_fee)
    cycle_started_at = time.monotonic()

    if not cycle.start():
        return "OUTSIDE"

    last_print = 0.0
    last_status_tg = 0.0
    waiting_after_session_end = False

    while True:
        stats = cycle.estimated_net_pnl()
        now = time.monotonic()

        # Track best values seen by the bot for post-analysis.
        if stats["net"] > cycle.best_net:
            cycle.best_net = stats["net"]
        if stats["exchange_unrealized"] > cycle.best_exchange_upnl:
            cycle.best_exchange_upnl = stats["exchange_unrealized"]

        # Fast entry detection by live position; avoids slow allOrders polling.
        cycle.mark_entry_from_stats(stats)

        # Adaptive neutral mode: while no position is filled, keep entry orders close to live price.
        if not cycle.entry_filled:
            cycle.reprice_entry_orders_if_needed(stats)

        # If native TP limit or manual close already closed the position, finish cleanly.
        if cycle.entry_filled and stats["position_amount"] <= 0:
            return finish_cycle_already_closed(cycle, cycle_started_at)

        # Make sure TP limit is on exchange if entry was detected but previous placement failed.
        if cycle.entry_filled and stats["position_amount"] > 0 and not cycle.tp_order_placed:
            cycle.place_native_tp_limit(stats)

        # Fast close decision BEFORE printing/Telegram.
        if cycle.entry_filled and stats["net"] >= TAKE_NET_PROFIT:
            return close_cycle(cycle, filters, "TP по Net est", stats, cycle_started_at, is_stop=False)

        if (
            cycle.entry_filled
            and TAKE_EXCHANGE_UPNL > 0
            and stats["exchange_unrealized"] >= TAKE_EXCHANGE_UPNL
            and stats["net"] >= EXCHANGE_TAKE_MIN_NET
        ):
            return close_cycle(
                cycle,
                filters,
                "TP по Binance PnL + Net guard",
                stats,
                cycle_started_at,
                is_stop=False,
            )

        if cycle.entry_filled and stats["net"] <= MAX_CYCLE_LOSS:
            return close_cycle(cycle, filters, "Stop по Net est", stats, cycle_started_at, is_stop=True)

        if now >= session_end and not waiting_after_session_end:
            if cycle.entry_filled or has_open_position():
                log("⏰ 4 години минули. Нові цикли не запускаю, чекаю закриття поточної позиції по Net est target/stop.", telegram=True)
                waiting_after_session_end = True
            else:
                log("⏰ 4 години минули. Входу ще не було — скасовую entry-ордери і завершую тест.", telegram=True)
                cancel_all_orders()
                time.sleep(0.5)
                return "TIME"

        if now - last_print >= PRINT_INTERVAL_SECONDS:
            line = (
                f"📊 Cycle #{cycle_number} | Time: {format_duration(now - cycle_started_at)} | "
                f"Net est: {stats['net']:+.4f} | "
                f"Best Net: {cycle.best_net:+.4f} | "
                f"Wallet Δ: {stats['wallet_change']:+.4f} | "
                f"Entry: {stats['active_side']} @ {round_tick(stats['active_entry_price'], filters['tick']) if stats['active_entry_price'] > 0 else stats['active_entry_price']} qty {stats['position_amount']} | "
                f"exchange uPnL: {stats['exchange_unrealized']:+.4f} | "
                f"Best uPnL: {cycle.best_exchange_upnl:+.4f} | "
                f"exec PnL: {stats['unrealized']:+.4f} | "
                f"bid/ask: {stats['bid']}/{stats['ask']} | "
                f"closePx: {stats['close_price']} | spread: {stats['spread']} | "
                f"fees: {stats['entry_fee_est']:.4f}+{stats['exit_fee_est']:.4f} | "
                f"mode: {cycle.last_analysis.get('mode', 'NA')} score: {cycle.last_analysis.get('score', 'NA')}"
            )
            log(line)
            last_print = now

        if (
            cycle.entry_filled
            and TELEGRAM_STATUS_EVERY_SECONDS > 0
            and now - last_status_tg >= TELEGRAM_STATUS_EVERY_SECONDS
        ):
            tg_send(
                f"📍 СТАТУС ПОЗИЦІЇ #{cycle_number}\n"
                f"Пара: {SYMBOL}\n"
                f"Напрямок: {side_ua(stats['active_side'])}\n"
                f"Вхід: {stats['active_entry_price']} | qty {stats['position_amount']}\n"
                f"Net est: {money(stats['net'])} USDT\n"
                f"Binance PnL: {money(stats['exchange_unrealized'])} USDT\n"
                f"Best Net / Best PnL: {money(cycle.best_net)} / {money(cycle.best_exchange_upnl)} USDT\n"
                f"Bid/Ask: {stats['bid']} / {stats['ask']} | spread {stats['spread']}\n"
                f"Час: {format_duration(now - cycle_started_at)}\n"
                f"TP: +{TAKE_NET_PROFIT} | SL: {MAX_CYCLE_LOSS}"
            )
            last_status_tg = now

        time.sleep(CHECK_INTERVAL_SECONDS)


# ============================================================
# MAIN LOOP
# ============================================================

def main() -> None:
    require_env()

    banner = (
        f"🤖 БОТ ЗАПУЩЕНО — v6.1.1 CLEAN TG\n"
        f"Режим: {trade_mode_label()} | Пара: {SYMBOL}\n"
        f"Час: {now_utc()}\n"
        f"Діапазон: {LOWER_PRICE} - {UPPER_PRICE}\n"
        f"Розмір входу: {ORDER_NOTIONAL_USDT} USDT номінал | плече {LEVERAGE}x\n"
        f"TP Net: +{TAKE_NET_PROFIT} USDT | SL: {MAX_CYCLE_LOSS} USDT\n"
        f"TP по Binance PnL: +{TAKE_EXCHANGE_UPNL} з Net guard {EXCHANGE_TAKE_MIN_NET}\n"
        f"TP-ордер на біржі: {'так' if USE_TP_LIMIT_ORDER else 'ні'}\n"
        f"Аналіз: {'увімкнено' if USE_SMART_ANALYSIS else 'вимкнено'} | підтвердження {SIGNAL_CONFIRM_SECONDS}s\n"
        f"Час роботи: {format_duration(TOTAL_RUNTIME_SECONDS)}\n"
        f"Telegram status: {'вимкнено' if TELEGRAM_STATUS_EVERY_SECONDS <= 0 else 'кожні ' + str(TELEGRAM_STATUS_EVERY_SECONDS) + 's'}"
    )
    log("\n" + "=" * 68)
    log(banner, telegram=True)
    log("=" * 68)

    sync_binance_time()
    filters = get_symbol_filters()

    if CLOSE_ON_START:
        log("🧹 Старт: скасовую старі ордери і закриваю старі позиції...")
        cleanup(filters, close_positions=True)
    else:
        log("🧹 Старт: скасовую тільки старі ордери, позиції не чіпаю...")
        cleanup(filters, close_positions=False)

    ensure_hedge_mode()
    set_isolated()
    set_leverage()

    taker_fee = get_taker_fee()
    log(f"⚙️ Taker fee: {(taker_fee * Decimal('100')):.4f}%")

    session_start_wallet = get_usdt_wallet_balance()
    session_start = time.monotonic()
    session_end = session_start + TOTAL_RUNTIME_SECONDS
    cycle_number = 1

    try:
        while time.monotonic() < session_end:
            try:
                result = run_cycle(cycle_number, filters, taker_fee, session_end)
            except Exception as error:
                # Last defense: do not kill Railway process on one unexpected error.
                log(f"🚨 Помилка циклу: {type(error).__name__}: {error}\nЧекаю {API_RETRY_SLEEP_SECONDS} сек і продовжую контроль.", telegram=True)
                time.sleep(API_RETRY_SLEEP_SECONDS)
                continue

            if result == "TIME":
                break

            if result == "OUTSIDE":
                log("⏳ Ціна поза діапазоном. Чекаю 10 секунд...")
                time.sleep(10)
                continue

            if result in {"TARGET", "STOP"}:
                remaining = session_end - time.monotonic()
                if remaining <= 0:
                    break

                pause_seconds = COOLDOWN_SECONDS if result == "TARGET" else LOSS_COOLDOWN_SECONDS
                log(f"☕ Пауза {pause_seconds} секунд...")
                time.sleep(min(pause_seconds, remaining))
                cycle_number += 1

    except KeyboardInterrupt:
        log("🛑 Тест зупинено вручну.", telegram=True)

    finally:
        log("\n🧹 Завершення тесту: скасовую ордери...")
        try:
            cleanup(filters, close_positions=CLOSE_ON_EXIT)
        except Exception as error:
            log(f"⚠️ Cleanup завершився з помилкою: {error}", telegram=True)

        final_wallet = get_usdt_wallet_balance()
        total_result = final_wallet - session_start_wallet
        elapsed_min = (time.monotonic() - session_start) / 60

        summary = (
            "📊 ПІДСУМОК СЕСІЇ\n"
            f"Пара: {SYMBOL}\n"
            f"Режим: {trade_mode_label()}\n"
            f"Час роботи: {elapsed_min:.1f} хв\n"
            f"Циклів: {cycle_number}\n"
            f"Стартовий баланс: {session_start_wallet:.4f} USDT\n"
            f"Фінальний баланс: {final_wallet:.4f} USDT\n"
            f"Загальний результат: {money(total_result)} USDT"
        )
        log("\n" + "=" * 68)
        log(summary, telegram=True)
        log("=" * 68)


if __name__ == "__main__":
    main()
