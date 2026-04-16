import logging
import time
from datetime import datetime, timezone

import requests
import pandas as pd

import config
import database

logger = logging.getLogger(__name__)


def get_current_price(symbol: str) -> float | None:
    """Fetch current price from Binance."""
    for attempt in range(1, 4):
        try:
            resp = requests.get(
                config.BINANCE_PRICE_URL,
                params={"symbol": symbol},
                timeout=10,
            )
            resp.raise_for_status()
            return float(resp.json()["price"])
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.warning("Price fetch attempt %d/3 for %s failed: %s", attempt, symbol, e)
            if attempt < 3:
                time.sleep(5)
    return None


def _fetch_klines_since(symbol: str, signal_time_str: str, interval: str = "15m") -> pd.DataFrame:
    """Fetch 15m candles from signal_time until now (up to 200 candles)."""
    signal_dt = datetime.strptime(signal_time_str, "%Y-%m-%d %H:%M:%S")
    start_ms = int(signal_dt.replace(tzinfo=timezone.utc).timestamp() * 1000)

    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ms,
        "limit": 200,
    }

    for attempt in range(1, 4):
        try:
            resp = requests.get(config.BINANCE_KLINES_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()

            df = pd.DataFrame(data, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades", "taker_buy_base",
                "taker_buy_quote", "ignore",
            ])
            for col in ["open", "high", "low", "close"]:
                df[col] = df[col].astype(float)

            return df
        except Exception as e:
            logger.warning("Klines fetch attempt %d/3 for %s failed: %s", attempt, symbol, e)
            if attempt < 3:
                time.sleep(5)

    return pd.DataFrame()


def _check_ohlc_outcome(sig: dict, klines: pd.DataFrame) -> tuple[str, float] | None:
    """Scan OHLC candles chronologically for TP/SL hits.

    Processes each candle in order and returns the FIRST outcome triggered:
      BUY  WIN  → candle high  >= take_profit
      BUY  LOSS → candle low   <= stop_loss
      SELL WIN  → candle low   <= take_profit
      SELL LOSS → candle high  >= stop_loss

    Returns (outcome, exit_price) or None if neither level was hit yet.
    """
    if klines.empty:
        return None

    is_buy = sig["signal_type"] == "STRONG_BUY"
    tp = sig["take_profit"]
    sl = sig["stop_loss"]

    for _, candle in klines.iterrows():
        high = float(candle["high"])
        low = float(candle["low"])

        if is_buy:
            if high >= tp:
                return "WIN", tp
            if low <= sl:
                return "LOSS", sl
        else:  # STRONG_SELL
            if low <= tp:
                return "WIN", tp
            if high >= sl:
                return "LOSS", sl

    return None


def check_outcomes() -> list[dict]:
    """Check all pending signals against TP/SL using OHLC candle data,
    falling back to current price only for EXPIRED resolution.
    Returns resolved signals."""
    pending = database.get_pending_signals()
    resolved = []

    for sig in pending:
        signal_time_str = sig["signal_time"]
        signal_dt = datetime.strptime(signal_time_str, "%Y-%m-%d %H:%M:%S")
        elapsed_minutes = int((datetime.utcnow() - signal_dt).total_seconds() / 60)
        elapsed_hours = elapsed_minutes / 60

        outcome = None
        exit_price = None
        pnl_pct = 0.0

        # ── Step 1: check via OHLC candles (catches TP/SL hits between scans) ──
        klines = _fetch_klines_since(sig["coin"], signal_time_str)
        ohlc_result = _check_ohlc_outcome(sig, klines)

        if ohlc_result:
            outcome, exit_price = ohlc_result
            if sig["signal_type"] == "STRONG_BUY":
                pnl_pct = round((exit_price - sig["entry_price"]) / sig["entry_price"] * 100, 2)
            else:
                pnl_pct = round((sig["entry_price"] - exit_price) / sig["entry_price"] * 100, 2)

        # ── Step 2: if no TP/SL hit and timeout reached → EXPIRED ──
        elif elapsed_hours >= config.OUTCOME_CHECK_HOURS:
            current_price = get_current_price(sig["coin"])
            if current_price is None:
                logger.warning("Could not fetch price for %s — skipping EXPIRED check", sig["coin"])
                continue
            outcome = "EXPIRED"
            exit_price = current_price
            if sig["signal_type"] == "STRONG_BUY":
                pnl_pct = round((current_price - sig["entry_price"]) / sig["entry_price"] * 100, 2)
            else:
                pnl_pct = round((sig["entry_price"] - current_price) / sig["entry_price"] * 100, 2)

        if outcome:
            database.resolve_signal(
                signal_id=sig["id"],
                outcome=outcome,
                exit_price=exit_price,
                pnl_pct=pnl_pct,
                duration_minutes=elapsed_minutes,
            )
            logger.info("%s signal #%d for %s resolved as %s (P&L: %.2f%%)",
                        sig["signal_type"], sig["id"], sig["coin"], outcome, pnl_pct)

            resolved_sig = database.get_signal_by_id(sig["id"])
            resolved.append(resolved_sig)

    return resolved
