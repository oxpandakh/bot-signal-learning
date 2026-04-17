import logging
from dataclasses import dataclass, field
from typing import Optional

import config
import database

logger = logging.getLogger(__name__)

MIN_SIGNAL_STRENGTH = config.MIN_SIGNAL_STRENGTH


def _round_price(price: float) -> float:
    if price >= 1000:
        return round(price, 2)
    elif price >= 1:
        return round(price, 4)
    elif price >= 0.01:
        return round(price, 6)
    elif price >= 0.0001:
        return round(price, 8)
    else:
        return round(price, 10)


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
    candle_patterns: list = field(default_factory=list)
    signal_time: str = ""  # UTC datetime string set after DB insert
    trend_score: int = 0
    trend_detail: dict = field(default_factory=dict)
    avg_1d:  float = None
    avg_7d:  float = None
    avg_30d: float = None
    trading_style: str = ""  # "Swing" or "Scalp"


_TREND_TFS = ["15m", "1h", "4h", "1d"]


def _compute_trend_score(coin_analysis: dict, is_buy: bool) -> tuple[int, dict]:
    """Count how many TFs align with the signal direction.
    BUY aligned:  RSI < 50 AND price > EMA50
    SELL aligned: RSI > 50 AND price < EMA50
    Returns (aligned_count, {tf: True/False/None})  — None means no data.
    """
    detail = {}
    score = 0
    for tf in _TREND_TFS:
        ind = coin_analysis.get(tf)
        if not ind:
            detail[tf] = None
            continue
        rsi = ind.get("rsi")
        price = ind.get("price")
        ema50 = ind.get("ema50")
        if rsi is None or price is None or ema50 is None:
            detail[tf] = None
            continue
        aligned = (rsi < 50 and price > ema50) if is_buy else (rsi > 50 and price < ema50)
        detail[tf] = aligned
        if aligned:
            score += 1
    return score, detail


_BULLISH_PATTERNS = {"Hammer", "Bullish Engulfing", "Morning Star", "Piercing Line"}
_BEARISH_PATTERNS = {"Shooting Star", "Bearish Engulfing", "Evening Star", "Dark Cloud Cover"}


def _rsi_points_buy(rsi: float) -> int:
    if rsi is None:
        return 0
    if rsi < 25:  return 15
    if rsi < 30:  return 12
    if rsi < 35:  return 9
    if rsi < 40:  return 5
    if rsi < 45:  return 2
    return 0


def _rsi_points_sell(rsi: float) -> int:
    if rsi is None:
        return 0
    if rsi > 80:  return 15
    if rsi > 75:  return 12
    if rsi > 70:  return 9
    if rsi > 65:  return 5
    if rsi > 60:  return 2
    return 0


def _volume_points(vol: float) -> int:
    if vol is None:
        return 0
    if vol >= 3.0:  return 10
    if vol >= 2.0:  return 8
    if vol >= 1.5:  return 5
    if vol >= 1.2:  return 2
    return 0


def _ema_alignment_points(ind: dict, is_buy: bool) -> int:
    """Grade EMA stack alignment. Max 10 pts.
    Bullish full stack: EMA20 > EMA50 > EMA200 (price above EMA50) = 10
    Price above EMA50 + EMA20 > EMA50 = 7
    Price above EMA50 only = 4
    """
    ema_pos = ind.get("ema_position")
    ema20 = ind.get("ema20")
    ema50 = ind.get("ema50")
    ema200 = ind.get("ema200")

    expected = "above_ema50" if is_buy else "below_ema50"
    if ema_pos != expected:
        return 0

    pts = 4
    if ema20 is not None and ema50 is not None:
        stack_ok = (ema20 > ema50) if is_buy else (ema20 < ema50)
        if stack_ok:
            pts = 7
            if ema200 is not None:
                full_stack = (ema20 > ema50 > ema200) if is_buy else (ema20 < ema50 < ema200)
                if full_stack:
                    pts = 10
    return pts


def _stoch_rsi_points(ind: dict, is_buy: bool) -> int:
    """Stochastic RSI confirmation. Max 10 pts.
    BUY: oversold (<20) + K crossing above D = strong.
    SELL: overbought (>80) + K crossing below D = strong.
    """
    k = ind.get("stoch_rsi_k")
    d = ind.get("stoch_rsi_d")
    if k is None or d is None:
        return 0

    if is_buy:
        if k < 0.20 and d < 0.20:
            return 10 if k > d else 6
        if k < 0.30 and k > d:
            return 4
        return 0
    else:
        if k > 0.80 and d > 0.80:
            return 10 if k < d else 6
        if k > 0.70 and k < d:
            return 4
        return 0


def _bb_points(ind: dict, is_buy: bool) -> int:
    """Bollinger Band position. Max 5 pts.
    BUY:  price near/below lower band = mean-reversion edge.
    SELL: price near/above upper band.
    """
    price = ind.get("price")
    bb_low = ind.get("bb_lower")
    bb_up = ind.get("bb_upper")
    if price is None or bb_low is None or bb_up is None:
        return 0
    width = bb_up - bb_low
    if width <= 0:
        return 0
    # Normalized position: 0 = lower band, 1 = upper band
    pos = (price - bb_low) / width

    if is_buy:
        if pos <= 0.05:  return 5
        if pos <= 0.20:  return 3
        if pos <= 0.35:  return 1
        return 0
    else:
        if pos >= 0.95:  return 5
        if pos >= 0.80:  return 3
        if pos >= 0.65:  return 1
        return 0


def _macd_points(ind: dict, is_buy: bool) -> int:
    """Graded MACD score. Max 15 pts.
    Fresh crossover in our direction = 15.
    No opposite crossover in the last bar, but still = 0 (only rewards active bias).
    """
    cross = ind.get("macd_cross")
    target = "bullish" if is_buy else "bearish"
    if cross == target:
        return 15
    return 0


def _multi_tf_points(all_timeframes: dict, is_buy: bool) -> tuple[int, int, int]:
    """Multi-timeframe alignment score. Max 15 pts.
    Returns (points, aligned_count, total_tfs_with_data).
    Higher timeframes (4h, 1d) weighted more than 15m/1h.
    """
    if not all_timeframes:
        return 0, 0, 0

    weights = {"15m": 2, "1h": 3, "4h": 4, "1d": 6}  # sums to 15
    pts = 0
    aligned = 0
    total = 0
    for tf, w in weights.items():
        ind = all_timeframes.get(tf)
        if not ind:
            continue
        rsi = ind.get("rsi")
        price = ind.get("price")
        ema50 = ind.get("ema50")
        if rsi is None or price is None or ema50 is None:
            continue
        total += 1
        is_aligned = (rsi < 50 and price > ema50) if is_buy else (rsi > 50 and price < ema50)
        if is_aligned:
            aligned += 1
            pts += w
    return pts, aligned, total


def _higher_tf_confirmation(all_timeframes: dict, is_buy: bool) -> int:
    """Reward when 4h/1d RSI not extreme against our direction. Max 5 pts."""
    if not all_timeframes:
        return 0
    pts = 0
    ind_4h = all_timeframes.get("4h") or {}
    ind_1d = all_timeframes.get("1d") or {}
    rsi_4h = ind_4h.get("rsi")
    rsi_1d = ind_1d.get("rsi")

    if is_buy:
        # We're buying — want higher TFs NOT overbought (not extended above).
        if rsi_4h is not None and rsi_4h < 60:
            pts += 2
        if rsi_1d is not None and rsi_1d < 60:
            pts += 3
    else:
        if rsi_4h is not None and rsi_4h > 40:
            pts += 2
        if rsi_1d is not None and rsi_1d > 40:
            pts += 3
    return pts


def _counter_trend_veto(all_timeframes: dict, is_buy: bool) -> Optional[str]:
    """Veto signals that fight a strong higher-timeframe trend.
    Returns a reason string if vetoed, else None.
    """
    if not all_timeframes:
        return None
    ind_4h = all_timeframes.get("4h") or {}
    ind_1d = all_timeframes.get("1d") or {}

    rsi_4h = ind_4h.get("rsi")
    rsi_1d = ind_1d.get("rsi")
    p_1d = ind_1d.get("price")
    ema200_1d = ind_1d.get("ema200")

    if is_buy:
        # Severely overbought on BOTH higher TFs → chasing a top.
        if rsi_4h is not None and rsi_1d is not None and rsi_4h > 78 and rsi_1d > 78:
            return f"4h RSI {rsi_4h:.1f} & 1d RSI {rsi_1d:.1f} severely overbought"
        # Price far below 1d EMA200 → strong downtrend, don't bottom-fish.
        if p_1d is not None and ema200_1d is not None and ema200_1d > 0:
            if p_1d < ema200_1d * 0.88:  # > 12% below EMA200
                return f"1d price {p_1d:.4f} is {100*(1-p_1d/ema200_1d):.1f}% below EMA200 (strong downtrend)"
    else:
        if rsi_4h is not None and rsi_1d is not None and rsi_4h < 22 and rsi_1d < 22:
            return f"4h RSI {rsi_4h:.1f} & 1d RSI {rsi_1d:.1f} severely oversold"
        if p_1d is not None and ema200_1d is not None and ema200_1d > 0:
            if p_1d > ema200_1d * 1.12:  # > 12% above EMA200
                return f"1d price {p_1d:.4f} is {100*(p_1d/ema200_1d-1):.1f}% above EMA200 (strong uptrend)"
    return None


def _calc_strength(ind_15m: dict, ind_1h: dict, all_timeframes: dict,
                   candle_patterns: list, is_buy: bool) -> tuple[float, dict]:
    """Compute graded signal strength 0-100% with a breakdown.

    Weights (sum = 100):
      RSI 15m        : 15
      RSI 1H         : 15
      MACD (1H)      : 15
      EMA alignment  : 10
      Volume (1H)    : 10
      Multi-TF align : 15
      Stoch RSI (1H) : 10
      BB position 1H :  5
      Higher-TF RSI  :  5
    Candles: +5 per matching pattern (cap +10), capped total at 100.
    """
    rsi_15m = ind_15m.get("rsi")
    rsi_1h = ind_1h.get("rsi")

    pts_rsi_15m = _rsi_points_buy(rsi_15m) if is_buy else _rsi_points_sell(rsi_15m)
    pts_rsi_1h  = _rsi_points_buy(rsi_1h)  if is_buy else _rsi_points_sell(rsi_1h)
    pts_macd    = _macd_points(ind_1h, is_buy)
    pts_ema     = _ema_alignment_points(ind_1h, is_buy)
    pts_vol     = _volume_points(ind_1h.get("volume_ratio"))
    pts_mtf, aligned_ct, total_tfs = _multi_tf_points(all_timeframes, is_buy)
    pts_stoch   = _stoch_rsi_points(ind_1h, is_buy)
    pts_bb      = _bb_points(ind_1h, is_buy)
    pts_htf     = _higher_tf_confirmation(all_timeframes, is_buy)

    base = (pts_rsi_15m + pts_rsi_1h + pts_macd + pts_ema + pts_vol
            + pts_mtf + pts_stoch + pts_bb + pts_htf)

    pattern_set = _BULLISH_PATTERNS if is_buy else _BEARISH_PATTERNS
    pts_candle = 0
    if candle_patterns:
        pts_candle = min(sum(5 for p in candle_patterns if p in pattern_set), 10)

    total = min(base + pts_candle, 100)

    breakdown = {
        "rsi_15m": pts_rsi_15m,
        "rsi_1h": pts_rsi_1h,
        "macd": pts_macd,
        "ema": pts_ema,
        "volume": pts_vol,
        "multi_tf": pts_mtf,
        "stoch_rsi": pts_stoch,
        "bollinger": pts_bb,
        "higher_tf": pts_htf,
        "candles": pts_candle,
        "mtf_aligned": f"{aligned_ct}/{total_tfs}" if total_tfs else "0/0",
    }
    return total, breakdown


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


def _trading_style(trend_score: int, trend_detail: dict) -> str:
    """Classify signal as Swing or Scalp based on multi-timeframe alignment.

    Swing  — higher timeframes (4h or 1d) confirm the direction AND ≥2 TFs aligned.
             These are trend-following setups suited for multi-hour/day holds.
    Scalp  — momentum driven mostly by the short-term TFs (15m/1h). Quick in-and-out.
    """
    tf_4h_aligned = trend_detail.get("4h") is True
    tf_1d_aligned = trend_detail.get("1d") is True
    higher_tf_confirmed = tf_4h_aligned or tf_1d_aligned

    if trend_score >= 2 and higher_tf_confirmed:
        return "Swing"
    return "Scalp"


def _build_signal(coin: str, signal_type: str, ind_15m: dict, ind_1h: dict,
                  all_timeframes: dict) -> Optional[Signal]:
    """Compute strength, apply veto, and build a Signal if it passes."""
    is_buy = signal_type == "STRONG_BUY"

    rsi_15m = ind_15m.get("rsi")
    rsi_1h = ind_1h.get("rsi")
    macd_cross = ind_1h.get("macd_cross")
    ema_position = ind_1h.get("ema_position")
    volume_ratio = ind_1h.get("volume_ratio")
    price = ind_1h.get("price")

    if any(v is None for v in [rsi_15m, rsi_1h, macd_cross, ema_position, volume_ratio, price]):
        return None

    # Require the right MACD direction as a hard gate — avoids firing on
    # pure oversold/overbought readings with no momentum confirmation.
    required_cross = "bullish" if is_buy else "bearish"
    if macd_cross != required_cross:
        return None

    # Combine patterns from both timeframes, deduplicated.
    patterns_15m = ind_15m.get("candle_patterns") or []
    patterns_1h  = ind_1h.get("candle_patterns") or []
    all_patterns = list(dict.fromkeys(patterns_15m + patterns_1h))

    # Counter-trend veto: don't fight a strong higher-TF trend.
    veto = _counter_trend_veto(all_timeframes, is_buy)
    if veto:
        logger.info("🚫 %s %s vetoed — %s", coin, signal_type, veto)
        return None

    strength, breakdown = _calc_strength(
        ind_15m, ind_1h, all_timeframes, all_patterns, is_buy
    )

    if strength < MIN_SIGNAL_STRENGTH:
        return None

    if is_buy:
        tp = _round_price(price * (1 + config.TAKE_PROFIT_PCT / 100))
        sl = _round_price(price * (1 - config.STOP_LOSS_PCT / 100))
        macd_label = "Bullish crossover"
    else:
        tp = _round_price(price * (1 - config.TAKE_PROFIT_PCT / 100))
        sl = _round_price(price * (1 + config.STOP_LOSS_PCT / 100))
        macd_label = "Bearish crossover"

    logger.info(
        "📐 %s %s breakdown → %s → %d%%",
        coin, signal_type, breakdown, int(strength),
    )

    return Signal(
        coin=coin,
        signal_type=signal_type,
        entry_price=price,
        take_profit=tp,
        stop_loss=sl,
        rsi_15m=rsi_15m,
        rsi_1h=rsi_1h,
        macd_cross=macd_label,
        volume_ratio=volume_ratio,
        ema_position=ema_position,
        strength=strength,
        candle_patterns=all_patterns,
    )


def check_strong_buy(coin: str, ind_15m: dict, ind_1h: dict,
                     all_timeframes: dict = None) -> Optional[Signal]:
    """Check if BUY signal strength >= MIN_SIGNAL_STRENGTH."""
    return _build_signal(coin, "STRONG_BUY", ind_15m, ind_1h, all_timeframes or {})


def check_strong_sell(coin: str, ind_15m: dict, ind_1h: dict,
                      all_timeframes: dict = None) -> Optional[Signal]:
    """Check if SELL signal strength >= MIN_SIGNAL_STRENGTH."""
    return _build_signal(coin, "STRONG_SELL", ind_15m, ind_1h, all_timeframes or {})


def generate_signals(analysis: dict) -> list[tuple[Signal, int]]:
    """Generate signals for all coins. Returns list of (Signal, signal_id) tuples."""
    fired = []

    for coin, timeframes in analysis.items():
        ind_15m = timeframes.get("15m")
        ind_1h = timeframes.get("1h")

        if not ind_15m or not ind_1h:
            logger.info("⏭️ %s — missing timeframe data, skipping", coin)
            continue

        rsi_15m = ind_15m.get("rsi") or 0
        rsi_1h = ind_1h.get("rsi") or 0
        macd = ind_1h.get("macd_cross", "none")
        ema = ind_1h.get("ema_position", "unknown")
        vol = ind_1h.get("volume_ratio") or 0

        patterns = list(dict.fromkeys(
            (ind_15m.get("candle_patterns") or []) + (ind_1h.get("candle_patterns") or [])
        ))
        buy_str, _ = _calc_strength(ind_15m, ind_1h, timeframes, patterns, is_buy=True)
        sell_str, _ = _calc_strength(ind_15m, ind_1h, timeframes, patterns, is_buy=False)

        logger.info("🔍 %s — BUY: %d%% | SELL: %d%% | RSI(15m:%.1f/1H:%.1f) MACD:%s EMA:%s Vol:%.2fx",
                     coin, buy_str, sell_str, rsi_15m, rsi_1h, macd, ema, vol)

        ind_1d = timeframes.get("1d")

        # Check STRONG BUY
        buy = check_strong_buy(coin, ind_15m, ind_1h, timeframes)
        if buy:
            buy.trend_score, buy.trend_detail = _compute_trend_score(timeframes, is_buy=True)
            buy.trading_style = _trading_style(buy.trend_score, buy.trend_detail)
            if ind_1d:
                buy.avg_1d  = ind_1d.get("avg_1d")
                buy.avg_7d  = ind_1d.get("avg_7d")
                buy.avg_30d = ind_1d.get("avg_30d")
            if database.has_pending_signal(coin, "STRONG_BUY"):
                logger.info("Skipping duplicate STRONG_BUY for %s (still pending)", coin)
            else:
                signal_id = database.insert_signal(
                    coin=buy.coin, signal_type=buy.signal_type,
                    entry_price=buy.entry_price, take_profit=buy.take_profit,
                    stop_loss=buy.stop_loss, rsi_15m=buy.rsi_15m,
                    rsi_1h=buy.rsi_1h, macd_cross=buy.macd_cross,
                    volume_ratio=buy.volume_ratio, ema_position=buy.ema_position,
                    strength=buy.strength,
                    avg_1d=buy.avg_1d, avg_7d=buy.avg_7d, avg_30d=buy.avg_30d,
                    trading_style=buy.trading_style,
                )
                sig_row = database.get_signal_by_id(signal_id)
                if sig_row:
                    buy.signal_time = sig_row["signal_time"]
                logger.info("🚀 STRONG BUY signal #%d for %s at $%.2f [%d%% %s]",
                            signal_id, coin, buy.entry_price, buy.strength,
                            _strength_label(buy.strength))
                fired.append((buy, signal_id))

        # Check STRONG SELL
        sell = check_strong_sell(coin, ind_15m, ind_1h, timeframes)
        if sell:
            sell.trend_score, sell.trend_detail = _compute_trend_score(timeframes, is_buy=False)
            sell.trading_style = _trading_style(sell.trend_score, sell.trend_detail)
            if ind_1d:
                sell.avg_1d  = ind_1d.get("avg_1d")
                sell.avg_7d  = ind_1d.get("avg_7d")
                sell.avg_30d = ind_1d.get("avg_30d")
            if database.has_pending_signal(coin, "STRONG_SELL"):
                logger.info("Skipping duplicate STRONG_SELL for %s (still pending)", coin)
            else:
                signal_id = database.insert_signal(
                    coin=sell.coin, signal_type=sell.signal_type,
                    entry_price=sell.entry_price, take_profit=sell.take_profit,
                    stop_loss=sell.stop_loss, rsi_15m=sell.rsi_15m,
                    rsi_1h=sell.rsi_1h, macd_cross=sell.macd_cross,
                    volume_ratio=sell.volume_ratio, ema_position=sell.ema_position,
                    strength=sell.strength,
                    avg_1d=sell.avg_1d, avg_7d=sell.avg_7d, avg_30d=sell.avg_30d,
                    trading_style=sell.trading_style,
                )
                sig_row = database.get_signal_by_id(signal_id)
                if sig_row:
                    sell.signal_time = sig_row["signal_time"]
                logger.info("🔴 STRONG SELL signal #%d for %s at $%.2f [%d%% %s]",
                            signal_id, coin, sell.entry_price, sell.strength,
                            _strength_label(sell.strength))
                fired.append((sell, signal_id))

    return fired
