import logging
from dataclasses import dataclass
from typing import Optional

import config
import database

logger = logging.getLogger(__name__)

MIN_SIGNAL_STRENGTH = 40  # Minimum % to fire a signal


@dataclass
class Signal:
    coin: str
    signal_type: str
    entry_price: float
    take_profit: float
    stop_loss: float
    rsi_15m: float
    rsi_1h: float
    macd_cross: str
    volume_ratio: float
    ema_position: str
    strength: float  # Signal strength percentage
    signal_time: str = ""  # UTC datetime string set after DB insert


def _calc_buy_strength(rsi_15m: float, rsi_1h: float, macd_cross: str,
                       ema_position: str, volume_ratio: float) -> float:
    """Calculate BUY signal strength from 0-100%.

    Scoring (total 100):
      RSI 15m (20pts): <30 = 20, <35 = 15, <40 = 10, <45 = 5
      RSI 1H  (20pts): <30 = 20, <35 = 15, <40 = 10, <45 = 5
      MACD    (25pts): bullish crossover = 25
      EMA     (15pts): above EMA50 = 15
      Volume  (20pts): >2.0x = 20, >1.5x = 15, >1.2x = 10, >1.0x = 5
    """
    score = 0

    # RSI 15m (20pts)
    if rsi_15m < 30:
        score += 20
    elif rsi_15m < 35:
        score += 15
    elif rsi_15m < 40:
        score += 10
    elif rsi_15m < 45:
        score += 5

    # RSI 1H (20pts)
    if rsi_1h < 30:
        score += 20
    elif rsi_1h < 35:
        score += 15
    elif rsi_1h < 40:
        score += 10
    elif rsi_1h < 45:
        score += 5

    # MACD (25pts)
    if macd_cross == "bullish":
        score += 25

    # EMA position (15pts)
    if ema_position == "above_ema50":
        score += 15

    # Volume (20pts)
    if volume_ratio > 2.0:
        score += 20
    elif volume_ratio > 1.5:
        score += 15
    elif volume_ratio > 1.2:
        score += 10
    elif volume_ratio > 1.0:
        score += 5

    return score


def _calc_sell_strength(rsi_15m: float, rsi_1h: float, macd_cross: str,
                        ema_position: str, volume_ratio: float) -> float:
    """Calculate SELL signal strength from 0-100%.

    Scoring (total 100):
      RSI 15m (20pts): >75 = 20, >70 = 15, >65 = 10, >60 = 5
      RSI 1H  (20pts): >75 = 20, >70 = 15, >65 = 10, >60 = 5
      MACD    (25pts): bearish crossover = 25
      EMA     (15pts): below EMA50 = 15
      Volume  (20pts): >2.0x = 20, >1.5x = 15, >1.2x = 10, >1.0x = 5
    """
    score = 0

    # RSI 15m (20pts)
    if rsi_15m > 75:
        score += 20
    elif rsi_15m > 70:
        score += 15
    elif rsi_15m > 65:
        score += 10
    elif rsi_15m > 60:
        score += 5

    # RSI 1H (20pts)
    if rsi_1h > 75:
        score += 20
    elif rsi_1h > 70:
        score += 15
    elif rsi_1h > 65:
        score += 10
    elif rsi_1h > 60:
        score += 5

    # MACD (25pts)
    if macd_cross == "bearish":
        score += 25

    # EMA position (15pts)
    if ema_position == "below_ema50":
        score += 15

    # Volume (20pts)
    if volume_ratio > 2.0:
        score += 20
    elif volume_ratio > 1.5:
        score += 15
    elif volume_ratio > 1.2:
        score += 10
    elif volume_ratio > 1.0:
        score += 5

    return score


def _strength_label(strength: float) -> str:
    if strength >= 90:
        return "🔥 EXTREME"
    elif strength >= 80:
        return "💪 VERY STRONG"
    elif strength >= 70:
        return "✅ STRONG"
    elif strength >= 60:
        return "⚡ MODERATE"
    elif strength >= 50:
        return "📊 FAIR"
    else:
        return "⚠️ WEAK"


def check_strong_buy(coin: str, ind_15m: dict, ind_1h: dict) -> Optional[Signal]:
    """Check if BUY signal strength >= 60%."""
    rsi_15m = ind_15m.get("rsi")
    rsi_1h = ind_1h.get("rsi")
    macd_cross = ind_1h.get("macd_cross")
    ema_position = ind_1h.get("ema_position")
    volume_ratio = ind_1h.get("volume_ratio")
    price = ind_1h.get("price")

    if any(v is None for v in [rsi_15m, rsi_1h, macd_cross, ema_position, volume_ratio, price]):
        return None

    strength = _calc_buy_strength(rsi_15m, rsi_1h, macd_cross, ema_position, volume_ratio)

    if strength >= MIN_SIGNAL_STRENGTH:
        tp = round(price * (1 + config.TAKE_PROFIT_PCT / 100), 2)
        sl = round(price * (1 - config.STOP_LOSS_PCT / 100), 2)

        return Signal(
            coin=coin,
            signal_type="STRONG_BUY",
            entry_price=price,
            take_profit=tp,
            stop_loss=sl,
            rsi_15m=rsi_15m,
            rsi_1h=rsi_1h,
            macd_cross="Bullish crossover",
            volume_ratio=volume_ratio,
            ema_position=ema_position,
            strength=strength,
        )

    return None


def check_strong_sell(coin: str, ind_15m: dict, ind_1h: dict) -> Optional[Signal]:
    """Check if SELL signal strength >= 60%."""
    rsi_15m = ind_15m.get("rsi")
    rsi_1h = ind_1h.get("rsi")
    macd_cross = ind_1h.get("macd_cross")
    ema_position = ind_1h.get("ema_position")
    volume_ratio = ind_1h.get("volume_ratio")
    price = ind_1h.get("price")

    if any(v is None for v in [rsi_15m, rsi_1h, macd_cross, ema_position, volume_ratio, price]):
        return None

    strength = _calc_sell_strength(rsi_15m, rsi_1h, macd_cross, ema_position, volume_ratio)

    if strength >= MIN_SIGNAL_STRENGTH:
        tp = round(price * (1 - config.TAKE_PROFIT_PCT / 100), 2)
        sl = round(price * (1 + config.STOP_LOSS_PCT / 100), 2)

        return Signal(
            coin=coin,
            signal_type="STRONG_SELL",
            entry_price=price,
            take_profit=tp,
            stop_loss=sl,
            rsi_15m=rsi_15m,
            rsi_1h=rsi_1h,
            macd_cross="Bearish crossover",
            volume_ratio=volume_ratio,
            ema_position=ema_position,
            strength=strength,
        )

    return None


def generate_signals(analysis: dict) -> list[tuple[Signal, int]]:
    """Generate signals for all coins. Returns list of (Signal, signal_id) tuples."""
    fired = []

    for coin, timeframes in analysis.items():
        ind_15m = timeframes.get("15m")
        ind_1h = timeframes.get("1h")

        if not ind_15m or not ind_1h:
            logger.info("⏭️ %s — missing timeframe data, skipping", coin)
            continue

        # Log signal check summary
        rsi_15m = ind_15m.get("rsi") or 0
        rsi_1h = ind_1h.get("rsi") or 0
        macd = ind_1h.get("macd_cross", "none")
        ema = ind_1h.get("ema_position", "unknown")
        vol = ind_1h.get("volume_ratio") or 0

        buy_str = _calc_buy_strength(rsi_15m, rsi_1h, macd, ema, vol)
        sell_str = _calc_sell_strength(rsi_15m, rsi_1h, macd, ema, vol)

        logger.info("🔍 %s — BUY: %d%% | SELL: %d%% | RSI(15m:%.1f/1H:%.1f) MACD:%s EMA:%s Vol:%.2fx",
                     coin, buy_str, sell_str, rsi_15m, rsi_1h, macd, ema, vol)

        # Check STRONG BUY
        buy = check_strong_buy(coin, ind_15m, ind_1h)
        if buy:
            if database.has_pending_signal(coin, "STRONG_BUY"):
                logger.info("Skipping duplicate STRONG_BUY for %s (still pending)", coin)
            else:
                signal_id = database.insert_signal(
                    coin=buy.coin, signal_type=buy.signal_type,
                    entry_price=buy.entry_price, take_profit=buy.take_profit,
                    stop_loss=buy.stop_loss, rsi_15m=buy.rsi_15m,
                    rsi_1h=buy.rsi_1h, macd_cross=buy.macd_cross,
                    volume_ratio=buy.volume_ratio, ema_position=buy.ema_position,
                )
                sig_row = database.get_signal_by_id(signal_id)
                if sig_row:
                    buy.signal_time = sig_row["signal_time"]
                logger.info("🚀 STRONG BUY signal #%d for %s at $%.2f [%d%% %s]",
                            signal_id, coin, buy.entry_price, buy.strength,
                            _strength_label(buy.strength))
                fired.append((buy, signal_id))

        # Check STRONG SELL
        sell = check_strong_sell(coin, ind_15m, ind_1h)
        if sell:
            if database.has_pending_signal(coin, "STRONG_SELL"):
                logger.info("Skipping duplicate STRONG_SELL for %s (still pending)", coin)
            else:
                signal_id = database.insert_signal(
                    coin=sell.coin, signal_type=sell.signal_type,
                    entry_price=sell.entry_price, take_profit=sell.take_profit,
                    stop_loss=sell.stop_loss, rsi_15m=sell.rsi_15m,
                    rsi_1h=sell.rsi_1h, macd_cross=sell.macd_cross,
                    volume_ratio=sell.volume_ratio, ema_position=sell.ema_position,
                )
                sig_row = database.get_signal_by_id(signal_id)
                if sig_row:
                    sell.signal_time = sig_row["signal_time"]
                logger.info("🔴 STRONG SELL signal #%d for %s at $%.2f [%d%% %s]",
                            signal_id, coin, sell.entry_price, sell.strength,
                            _strength_label(sell.strength))
                fired.append((sell, signal_id))

    return fired
