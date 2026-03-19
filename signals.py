import logging
from dataclasses import dataclass
from typing import Optional

import config
import database

logger = logging.getLogger(__name__)


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


def check_strong_buy(coin: str, ind_15m: dict, ind_1h: dict) -> Optional[Signal]:
    """Check if STRONG BUY conditions are met (all must be true)."""
    rsi_15m = ind_15m.get("rsi")
    rsi_1h = ind_1h.get("rsi")
    macd_cross = ind_1h.get("macd_cross")
    ema_position = ind_1h.get("ema_position")
    volume_ratio = ind_1h.get("volume_ratio")
    price = ind_1h.get("price")

    if any(v is None for v in [rsi_15m, rsi_1h, macd_cross, ema_position, volume_ratio, price]):
        return None

    # All conditions must be true
    if (rsi_15m < config.RSI_OVERSOLD
            and rsi_1h < config.RSI_OVERSOLD
            and macd_cross == "bullish"
            and ema_position == "above_ema50"
            and volume_ratio > config.VOLUME_THRESHOLD):

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
        )

    return None


def check_strong_sell(coin: str, ind_15m: dict, ind_1h: dict) -> Optional[Signal]:
    """Check if STRONG SELL conditions are met (all must be true)."""
    rsi_15m = ind_15m.get("rsi")
    rsi_1h = ind_1h.get("rsi")
    macd_cross = ind_1h.get("macd_cross")
    ema_position = ind_1h.get("ema_position")
    volume_ratio = ind_1h.get("volume_ratio")
    price = ind_1h.get("price")

    if any(v is None for v in [rsi_15m, rsi_1h, macd_cross, ema_position, volume_ratio, price]):
        return None

    if (rsi_15m > config.RSI_OVERBOUGHT
            and rsi_1h > config.RSI_OVERBOUGHT
            and macd_cross == "bearish"
            and ema_position == "below_ema50"
            and volume_ratio > config.VOLUME_THRESHOLD):

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
        )

    return None


def generate_signals(analysis: dict) -> list[Signal]:
    """Generate signals for all coins based on analysis results."""
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

        buy_checks = [
            ("RSI 15m < 35", rsi_15m < config.RSI_OVERSOLD, f"{rsi_15m:.1f}"),
            ("RSI 1H < 35", rsi_1h < config.RSI_OVERSOLD, f"{rsi_1h:.1f}"),
            ("MACD bullish", macd == "bullish", macd),
            ("Above EMA50", ema == "above_ema50", ema),
            ("Vol > 1.5x", vol > config.VOLUME_THRESHOLD, f"{vol:.2f}x"),
        ]
        sell_checks = [
            ("RSI 15m > 70", rsi_15m > config.RSI_OVERBOUGHT, f"{rsi_15m:.1f}"),
            ("RSI 1H > 70", rsi_1h > config.RSI_OVERBOUGHT, f"{rsi_1h:.1f}"),
            ("MACD bearish", macd == "bearish", macd),
            ("Below EMA50", ema == "below_ema50", ema),
            ("Vol > 1.5x", vol > config.VOLUME_THRESHOLD, f"{vol:.2f}x"),
        ]

        buy_pass = sum(1 for _, ok, _ in buy_checks if ok)
        sell_pass = sum(1 for _, ok, _ in sell_checks if ok)

        if buy_pass < 5 and sell_pass < 5:
            buy_detail = " | ".join(f"{'✅' if ok else '❌'}{name}({val})" for name, ok, val in buy_checks)
            sell_detail = " | ".join(f"{'✅' if ok else '❌'}{name}({val})" for name, ok, val in sell_checks)
            logger.info("🔍 %s — BUY[%d/5]: %s", coin, buy_pass, buy_detail)
            logger.info("🔍 %s — SELL[%d/5]: %s", coin, sell_pass, sell_detail)

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
                logger.info("🚀 STRONG BUY signal #%d for %s at $%.2f",
                            signal_id, coin, buy.entry_price)
                fired.append(buy)

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
                logger.info("🔴 STRONG SELL signal #%d for %s at $%.2f",
                            signal_id, coin, sell.entry_price)
                fired.append(sell)

    return fired
