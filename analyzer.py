import logging

import pandas as pd
from ta.momentum import RSIIndicator, StochRSIIndicator
from ta.trend import MACD, EMAIndicator
from ta.volatility import BollingerBands

import config

logger = logging.getLogger(__name__)


def compute_indicators(df: pd.DataFrame) -> dict:
    """Compute all technical indicators for a given OHLCV DataFrame.
    Returns a dict with the latest indicator values."""
    if df.empty or len(df) < config.EMA_PERIODS[-1]:
        return {}

    close = df["close"]
    volume = df["volume"]

    # RSI
    rsi_ind = RSIIndicator(close, window=config.RSI_PERIOD)
    rsi = rsi_ind.rsi()

    # MACD
    macd_ind = MACD(close, window_fast=config.MACD_FAST,
                    window_slow=config.MACD_SLOW, window_sign=config.MACD_SIGNAL)
    macd_line = macd_ind.macd()
    macd_signal = macd_ind.macd_signal()

    # Bollinger Bands
    bb_ind = BollingerBands(close, window=config.BB_PERIOD)

    # EMAs
    ema20 = EMAIndicator(close, window=20).ema_indicator()
    ema50 = EMAIndicator(close, window=50).ema_indicator()
    ema200 = EMAIndicator(close, window=200).ema_indicator()

    # Volume ratio
    vol_avg = volume.rolling(window=config.VOLUME_AVG_PERIOD).mean()
    vol_ratio = volume / vol_avg

    # Stochastic RSI
    stoch_rsi_ind = StochRSIIndicator(close, window=config.RSI_PERIOD)

    # Get latest values safely
    latest = len(df) - 1

    def safe_val(series, idx=latest):
        if series is None or series.empty or idx >= len(series):
            return None
        val = series.iloc[idx]
        return None if pd.isna(val) else float(val)

    # MACD crossover detection
    macd_cross = "none"
    if macd_line is not None and macd_signal is not None and len(macd_line) >= 2:
        macd_now = safe_val(macd_line)
        signal_now = safe_val(macd_signal)
        macd_prev = safe_val(macd_line, latest - 1)
        signal_prev = safe_val(macd_signal, latest - 1)

        if all(v is not None for v in [macd_now, signal_now, macd_prev, signal_prev]):
            if macd_prev <= signal_prev and macd_now > signal_now:
                macd_cross = "bullish"
            elif macd_prev >= signal_prev and macd_now < signal_now:
                macd_cross = "bearish"

    # EMA position
    price = safe_val(close)
    ema50_val = safe_val(ema50)
    ema_position = "unknown"
    if price is not None and ema50_val is not None:
        ema_position = "above_ema50" if price > ema50_val else "below_ema50"

    result = {
        "rsi": safe_val(rsi),
        "macd_cross": macd_cross,
        "ema20": safe_val(ema20),
        "ema50": safe_val(ema50),
        "ema200": safe_val(ema200),
        "ema_position": ema_position,
        "volume_ratio": safe_val(vol_ratio),
        "price": price,
        "bb_upper": safe_val(bb_ind.bollinger_hband()),
        "bb_mid": safe_val(bb_ind.bollinger_mavg()),
        "bb_lower": safe_val(bb_ind.bollinger_lband()),
        "stoch_rsi_k": safe_val(stoch_rsi_ind.stochrsi_k()),
        "stoch_rsi_d": safe_val(stoch_rsi_ind.stochrsi_d()),
    }

    return result


def analyze_all(market_data: dict) -> dict:
    """Analyze all coins across all timeframes.
    Returns: {coin: {timeframe: indicators_dict}}"""
    analysis = {}

    for coin, timeframes in market_data.items():
        analysis[coin] = {}
        for tf, df in timeframes.items():
            indicators = compute_indicators(df)
            if indicators:
                analysis[coin][tf] = indicators
                logger.info("📊 %s %s — RSI: %.1f | MACD: %s | EMA: %s | Vol: %.2fx | Price: $%.4f",
                            coin, tf,
                            indicators.get("rsi") or 0,
                            indicators.get("macd_cross", "n/a"),
                            indicators.get("ema_position", "n/a"),
                            indicators.get("volume_ratio") or 0,
                            indicators.get("price") or 0)
            else:
                logger.warning("⚠️ %s %s — insufficient data for indicators", coin, tf)

    return analysis
