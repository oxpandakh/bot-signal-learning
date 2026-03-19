import time
import logging

import requests
import pandas as pd

import config

logger = logging.getLogger(__name__)


def fetch_klines(symbol: str, interval: str, limit: int = config.CANDLE_LIMIT) -> pd.DataFrame:
    """Fetch OHLCV candles from Binance REST API with retry logic."""
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
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

            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = df[col].astype(float)

            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
            df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")

            return df

        except (requests.RequestException, ValueError) as e:
            logger.warning("Binance API attempt %d/3 for %s %s failed: %s",
                           attempt, symbol, interval, e)
            if attempt < 3:
                time.sleep(5)

    logger.error("Failed to fetch klines for %s %s after 3 retries", symbol, interval)
    return pd.DataFrame()


def scan_all_coins() -> dict:
    """Fetch candles for all coins and both timeframes. Returns nested dict."""
    results = {}

    for coin in config.COINS:
        results[coin] = {}
        for tf in config.TIMEFRAMES:
            df = fetch_klines(coin, tf)
            if not df.empty:
                results[coin][tf] = df
                logger.info("Fetched %d candles for %s %s", len(df), coin, tf)
            else:
                logger.warning("No data for %s %s — skipping", coin, tf)

    return results
