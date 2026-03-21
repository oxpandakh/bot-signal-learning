import logging
from datetime import datetime, timezone, timedelta

from telegram import Update, ReplyParameters
from telegram.ext import Application, CommandHandler, ContextTypes

# Cambodia (Phnom Penh) timezone — UTC+7
TZ_CAMBODIA = timezone(timedelta(hours=7))

import config
import database
from signals import Signal

logger = logging.getLogger(__name__)

app: Application = None


def build_app() -> Application:
    """Build and configure the Telegram bot application."""
    global app
    app = (
        Application.builder()
        .token(config.TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("winrate", cmd_winrate))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("best", cmd_best))
    app.add_handler(CommandHandler("worst", cmd_worst))
    app.add_handler(CommandHandler("pending", cmd_pending))
    app.add_handler(CommandHandler("history", cmd_history))

    return app


# ──────────── Message formatting helpers ────────────

def format_price(price: float) -> str:
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:.2f}"
    elif price >= 0.01:
        return f"${price:.4f}"
    elif price >= 0.0001:
        return f"${price:.6f}"
    else:
        return f"${price:.8f}"


def format_time_now() -> str:
    """Format current time in both UTC and Cambodia timezone."""
    utc_now = datetime.now(timezone.utc)
    cam_now = utc_now.astimezone(TZ_CAMBODIA)
    return f"{utc_now.strftime('%d %b %Y %H:%M')} UTC | {cam_now.strftime('%H:%M')} UTC+7"


def format_time_str(time_str: str) -> str:
    """Convert a UTC datetime string to both UTC and Cambodia timezone display."""
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc)
        dt_cam = dt.astimezone(TZ_CAMBODIA)
        return f"{dt.strftime('%d %b %Y %H:%M')} UTC | {dt_cam.strftime('%H:%M')} UTC+7"
    except (ValueError, TypeError):
        return str(time_str)


def format_duration(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


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


def _strength_bar(strength: float) -> str:
    filled = round(strength / 10)
    return "█" * filled + "░" * (10 - filled)


def _signal_title(signal_type: str, strength: float) -> tuple[str, str]:
    """Return (emoji, label) based on signal type and strength."""
    direction = "BUY" if "BUY" in signal_type else "SELL"
    if strength >= 90:
        return ("🔥", f"EXTREME {direction}")
    elif strength >= 80:
        return ("💪", f"VERY STRONG {direction}")
    elif strength >= 70:
        return ("✅", f"STRONG {direction}")
    elif strength >= 60:
        return ("⚡", f"MODERATE {direction}")
    elif strength >= 50:
        return ("📊", f"FAIR {direction}")
    else:
        return ("⚠️", f"WEAK {direction}")


def _format_trend_score(sig: Signal) -> str:
    if not sig.trend_detail:
        return ""
    parts = []
    for tf in ["15m", "1h", "4h", "1d"]:
        v = sig.trend_detail.get(tf)
        icon = "🟢" if v is True else "🔴" if v is False else "⚫"
        parts.append(f"{icon}{tf}")
    total = sum(1 for v in sig.trend_detail.values() if v is not None)
    return f"📡 TF Align  {sig.trend_score}/{total}   {'  '.join(parts)}\n"


def format_signal_alert(sig: Signal) -> str:
    emoji, label = _signal_title(sig.signal_type, sig.strength)
    tp_pct = config.TAKE_PROFIT_PCT
    sl_pct = config.STOP_LOSS_PCT
    vol_pct = round((sig.volume_ratio - 1) * 100)
    strength = sig.strength
    s_label = _strength_label(strength)
    s_bar = _strength_bar(strength)
    is_buy = "BUY" in sig.signal_type
    tp_arrow = "↑" if is_buy else "↓"
    sl_arrow = "↓" if is_buy else "↑"

    return (
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"📶  {strength:.0f}%  {s_bar}  {s_label}\n"
        f"\n"
        f"💰 Entry   {format_price(sig.entry_price)}\n"
        f"🎯 Target  {format_price(sig.take_profit)}   {tp_arrow} {tp_pct}%\n"
        f"🛑 Stop    {format_price(sig.stop_loss)}   {sl_arrow} {sl_pct}%\n"
        f"\n"
        f"📊 RSI   15m {sig.rsi_15m:.1f}  ·  1H {sig.rsi_1h:.1f}\n"
        + _format_trend_score(sig)
        + f"📈 MACD  {sig.macd_cross}\n"
        f"📦 Vol   +{vol_pct}% above avg\n"
        f"⏱  15m + 1H confluence\n"
        + (f"🕯 Candles  {'  ·  '.join(sig.candle_patterns)}\n" if sig.candle_patterns else "")
        + f"\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Not financial advice"
    )


def format_outcome(sig: dict) -> str:
    outcome = sig["outcome"]
    coin = sig["coin"]
    signal_type = sig["signal_type"].replace("_", " ")
    entry = format_price(sig["entry_price"])
    exit_p = format_price(sig["exit_price"])
    pnl = sig["pnl_pct"]
    pnl_str = f"+{pnl}%" if pnl >= 0 else f"{pnl}%"
    duration = format_duration(sig["duration_minutes"])

    # Fetch stats
    coin_stats = database.get_coin_stats()
    signal_stats = database.get_signal_stats()

    coin_stat = next((c for c in coin_stats if c["coin"] == coin), None)
    sig_stat = next((s for s in signal_stats if s["signal_type"] == sig["signal_type"]), None)

    stats_block = ""
    if coin_stat or sig_stat:
        stats_block = "━━━━━━━━━━━━━━━━━━━━━━━\n"
        if coin_stat:
            stats_block += f"📊 {coin}   {coin_stat['wins']}W / {coin_stat['losses']}L → {coin_stat['win_rate']:.1f}%\n"
        if sig_stat:
            stats_block += f"📊 {signal_type}   {sig_stat['wins']}W / {sig_stat['losses']}L → {sig_stat['win_rate']:.1f}%\n"

    if outcome == "WIN":
        return (
            f"✅ WIN — {coin}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"📣 {signal_type}\n"
            f"💰 Entry   {entry}  →  📍 {exit_p}\n"
            f"🎯 Target  {format_price(sig['take_profit'])}\n"
            f"\n"
            f"💵 P&L  {pnl_str}   ·   ⏳ {duration}\n"
            f"\n"
            f"{stats_block}"
            f"⚠️ Not financial advice"
        )
    elif outcome == "LOSS":
        return (
            f"❌ LOSS — {coin}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"📣 {signal_type}\n"
            f"💰 Entry   {entry}  →  📍 {exit_p}\n"
            f"🛑 Stop    {format_price(sig['stop_loss'])}\n"
            f"\n"
            f"💵 P&L  {pnl_str}   ·   ⏳ {duration}\n"
            f"\n"
            f"{stats_block}"
            f"⚠️ Not financial advice"
        )
    else:  # EXPIRED
        return (
            f"⏳ EXPIRED — {coin}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"\n"
            f"📣 {signal_type}\n"
            f"💰 Entry      {entry}\n"
            f"📍 At expiry  {exit_p}\n"
            f"\n"
            f"💵 Unrealized  {pnl_str}   ·   ⏳ {config.OUTCOME_CHECK_HOURS}h timeout\n"
            f"\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ Not financial advice"
        )


def format_daily_summary() -> str:
    today_sigs = database.get_yesterday_signals()
    total = len(today_sigs)
    wins = sum(1 for s in today_sigs if s["outcome"] == "WIN")
    losses = sum(1 for s in today_sigs if s["outcome"] == "LOSS")
    pending = sum(1 for s in today_sigs if s["outcome"] == "PENDING")
    expired = sum(1 for s in today_sigs if s["outcome"] == "EXPIRED")

    win_pct = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

    yesterday_utc = (datetime.now(timezone.utc) - timedelta(days=1))
    today_str = yesterday_utc.strftime("%d %b %Y")

    # By signal type
    buy_wins = sum(1 for s in today_sigs if s["signal_type"] == "STRONG_BUY" and s["outcome"] == "WIN")
    buy_losses = sum(1 for s in today_sigs if s["signal_type"] == "STRONG_BUY" and s["outcome"] == "LOSS")
    sell_wins = sum(1 for s in today_sigs if s["signal_type"] == "STRONG_SELL" and s["outcome"] == "WIN")
    sell_losses = sum(1 for s in today_sigs if s["signal_type"] == "STRONG_SELL" and s["outcome"] == "LOSS")

    buy_rate = (buy_wins / (buy_wins + buy_losses) * 100) if (buy_wins + buy_losses) > 0 else 0
    sell_rate = (sell_wins / (sell_wins + sell_losses) * 100) if (sell_wins + sell_losses) > 0 else 0

    # By coin
    coin_map = {}
    for s in today_sigs:
        if s["outcome"] in ("WIN", "LOSS"):
            c = s["coin"]
            if c not in coin_map:
                coin_map[c] = {"wins": 0, "losses": 0}
            if s["outcome"] == "WIN":
                coin_map[c]["wins"] += 1
            else:
                coin_map[c]["losses"] += 1

    coin_lines = ""
    for c, v in sorted(coin_map.items()):
        w, l = v["wins"], v["losses"]
        r = (w / (w + l) * 100) if (w + l) > 0 else 0
        coin_lines += f"  {c}   {w}W / {l}L  →  {r:.1f}%\n"

    # Best / worst
    best_coin, best_rate = "", 0
    worst_coin, worst_rate = "", 100
    for c, v in coin_map.items():
        w, l = v["wins"], v["losses"]
        r = (w / (w + l) * 100) if (w + l) > 0 else 0
        if r >= best_rate:
            best_rate = r
            best_coin = c
        if r <= worst_rate:
            worst_rate = r
            worst_coin = c

    # Best/worst signal type
    best_sig = "STRONG BUY" if buy_rate >= sell_rate else "STRONG SELL"
    worst_sig = "STRONG SELL" if buy_rate >= sell_rate else "STRONG BUY"

    alltime = database.get_alltime_win_rate()

    msg = (
        f"📊 DAILY SIGNAL REPORT — {today_str}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Total Signals : {total}\n"
        f"✅ Wins       : {wins}    ({win_pct:.1f}%)\n"
        f"❌ Losses     : {losses}    ({(losses / (wins + losses) * 100) if (wins + losses) > 0 else 0:.1f}%)\n"
        f"⏳ Pending    : {pending}\n"
    )
    if expired:
        msg += f"⏳ Expired    : {expired}\n"

    msg += (
        f"\n📈 BY SIGNAL TYPE:\n"
        f"  🟢 STRONG BUY   → {buy_wins}W / {buy_losses}L  →  {buy_rate:.1f}%\n"
        f"  🔴 STRONG SELL  → {sell_wins}W / {sell_losses}L  →  {sell_rate:.1f}%\n"
        f"\n🪙 BY COIN:\n"
        f"{coin_lines}"
    )

    if best_coin:
        msg += f"\n🏆 Best Signal  : {best_sig} on {best_coin} ({best_rate:.0f}%)\n"
    if worst_coin:
        msg += f"💀 Worst Signal : {worst_sig} on {worst_coin} ({worst_rate:.0f}%)\n"

    msg += (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 All-time overall win rate: {alltime:.1f}%\n"
        f"⚠️ Not financial advice"
    )

    return msg


# ──────────── Sending helpers ────────────

async def send_message(text: str, reply_to_message_id: int = None) -> int | None:
    """Send a message to the configured Telegram chat. Returns message_id."""
    if not app or not app.bot:
        logger.error("Telegram bot not initialized")
        return None
    try:
        kwargs = {"chat_id": config.TELEGRAM_CHAT_ID, "text": text}
        if reply_to_message_id:
            kwargs["reply_parameters"] = ReplyParameters(
                message_id=reply_to_message_id,
                chat_id=config.TELEGRAM_CHAT_ID,
            )
        msg = await app.bot.send_message(**kwargs)
        return msg.message_id
    except Exception as e:
        logger.error("Failed to send Telegram message: %s", e, exc_info=True)
        return None


async def send_signal_alert(signal: Signal, signal_id: int):
    """Send signal alert and store the Telegram message_id in DB."""
    message_id = await send_message(format_signal_alert(signal))
    if message_id and signal_id:
        database.set_telegram_message_id(signal_id, message_id)
        logger.info("Stored telegram_message_id=%d for signal #%d", message_id, signal_id)
    else:
        logger.warning("Failed to store telegram_message_id for signal #%d", signal_id)


async def send_outcome(sig: dict):
    """Send outcome as a reply to the original signal message."""
    reply_to = sig.get("telegram_message_id")
    if not reply_to:
        logger.warning("No telegram_message_id for signal #%d — sending without reply", sig.get("id"))
    await send_message(format_outcome(sig), reply_to_message_id=reply_to)


async def send_daily_summary():
    await send_message(format_daily_summary())


async def send_startup_message():
    coins = ", ".join(config.COINS[:3]) + "..."
    msg = f"🤖 Crypto Signal Bot started! Scanning {coins} every {config.SCAN_INTERVAL_MINUTES} minutes."
    await send_message(msg)


# ──────────── Command handlers ────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "🤖 *Crypto Signal Bot*\n\n"
        "I scan 10 crypto pairs on Binance every 15 minutes using RSI, MACD, "
        "Bollinger Bands, EMAs, and volume analysis across 15m and 1H timeframes.\n\n"
        "I only fire *STRONG* signals when both timeframes agree (confluence).\n\n"
        "*Commands:*\n"
        "/winrate — All-time win rate by type & coin\n"
        "/stats — Today's performance summary\n"
        "/best — Top 3 coins by win rate\n"
        "/worst — Bottom 3 coins by win rate\n"
        "/pending — Open/unresolved signals\n"
        "/history N — Last N resolved signals (default 5)\n\n"
        "⚠️ Not financial advice"
    )
    await update.message.reply_text(msg, parse_mode="Markdown")


async def cmd_winrate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    alltime = database.get_alltime_win_rate()
    sig_stats = database.get_signal_stats()
    coin_stats = database.get_coin_stats()

    msg = f"📊 ALL-TIME WIN RATE: {alltime:.1f}%\n━━━━━━━━━━━━━━━━━━━━\n\n"

    msg += "📈 BY SIGNAL TYPE:\n"
    for s in sig_stats:
        msg += f"  {s['signal_type'].replace('_', ' ')}: {s['win_rate']:.1f}% ({s['wins']}W / {s['losses']}L / {s['expired']}E)\n"

    msg += "\n🪙 BY COIN:\n"
    for c in coin_stats:
        msg += f"  {c['coin']}: {c['win_rate']:.1f}% ({c['wins']}W / {c['losses']}L / {c['expired']}E)\n"

    if not sig_stats and not coin_stats:
        msg += "No resolved signals yet.\n"

    msg += "\n⚠️ Not financial advice"
    await update.message.reply_text(msg)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(format_daily_summary())


async def cmd_best(update: Update, context: ContextTypes.DEFAULT_TYPE):
    best = database.get_best_coins(3)
    if not best:
        await update.message.reply_text("Not enough data yet (need min 3 signals per coin).")
        return

    msg = "🏆 TOP 3 COINS BY WIN RATE\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, c in enumerate(best, 1):
        msg += f"{i}. {c['coin']} — {c['win_rate']:.1f}% ({c['wins']}W / {c['losses']}L)\n"
    msg += "\n⚠️ Not financial advice"
    await update.message.reply_text(msg)


async def cmd_worst(update: Update, context: ContextTypes.DEFAULT_TYPE):
    worst = database.get_worst_coins(3)
    if not worst:
        await update.message.reply_text("Not enough data yet (need min 3 signals per coin).")
        return

    msg = "💀 BOTTOM 3 COINS BY WIN RATE\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for i, c in enumerate(worst, 1):
        msg += f"{i}. {c['coin']} — {c['win_rate']:.1f}% ({c['wins']}W / {c['losses']}L)\n"
    msg += "\n⚠️ Not financial advice"
    await update.message.reply_text(msg)


async def cmd_pending(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pending = database.get_pending_signals()
    if not pending:
        await update.message.reply_text("No pending signals at the moment.")
        return

    msg = f"⏳ PENDING SIGNALS ({len(pending)})\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for s in pending:
        signal_time = datetime.strptime(s["signal_time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        elapsed = int((datetime.now(timezone.utc) - signal_time).total_seconds() / 60)
        msg += (
            f"{'🟢' if s['signal_type'] == 'STRONG_BUY' else '🔴'} {s['coin']} — "
            f"{s['signal_type'].replace('_', ' ')}\n"
            f"   Entry: {format_price(s['entry_price'])} | "
            f"TP: {format_price(s['take_profit'])} | "
            f"SL: {format_price(s['stop_loss'])}\n"
            f"   Opened {format_duration(elapsed)} ago\n\n"
        )
    msg += "⚠️ Not financial advice"
    await update.message.reply_text(msg)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        n = int(context.args[0]) if context.args else 5
    except (ValueError, IndexError):
        n = 5

    history = database.get_last_resolved(n)
    if not history:
        await update.message.reply_text("No resolved signals yet.")
        return

    msg = f"📜 LAST {len(history)} RESOLVED SIGNALS\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for s in history:
        icon = "✅" if s["outcome"] == "WIN" else ("❌" if s["outcome"] == "LOSS" else "⏳")
        msg += (
            f"{icon} {s['coin']} — {s['signal_type'].replace('_', ' ')} — {s['outcome']}\n"
            f"   Entry: {format_price(s['entry_price'])} → Exit: {format_price(s['exit_price'])}\n"
            f"   P&L: {'+' if s['pnl_pct'] >= 0 else ''}{s['pnl_pct']}% | "
            f"Duration: {format_duration(s['duration_minutes'])}\n"
            f"   {format_time_str(s['outcome_time'])}\n\n"
        )
    msg += "⚠️ Not financial advice"
    await update.message.reply_text(msg)
