import logging
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

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
    else:
        return f"${price:.4f}"


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


def format_signal_alert(sig: Signal) -> str:
    emoji, label = _signal_title(sig.signal_type, sig.strength)
    tp_pct = config.TAKE_PROFIT_PCT
    sl_pct = config.STOP_LOSS_PCT
    vol_pct = round((sig.volume_ratio - 1) * 100)
    now = datetime.utcnow().strftime("%d %b %Y %H:%M UTC")
    strength = sig.strength
    s_label = _strength_label(strength)
    s_bar = _strength_bar(strength)

    return (
        f"{emoji} {label} — {sig.coin}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📶 Strength   : {strength:.0f}% {s_label}\n"
        f"   {s_bar}\n"
        f"💰 Entry Price : {format_price(sig.entry_price)}\n"
        f"🎯 Take Profit : {format_price(sig.take_profit)}  (+{tp_pct}%)\n"
        f"🛑 Stop Loss   : {format_price(sig.stop_loss)}  (-{sl_pct}%)\n"
        f"📊 RSI 15m     : {sig.rsi_15m:.1f}\n"
        f"📊 RSI 1H      : {sig.rsi_1h:.1f}\n"
        f"📈 MACD        : {sig.macd_cross}\n"
        f"📦 Volume      : +{vol_pct}% above avg\n"
        f"⏱ Confluence  : 15m + 1H\n"
        f"🕐 Time        : {now}\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚠️ Not financial advice"
    )


def format_outcome(sig: dict) -> str:
    outcome = sig["outcome"]
    coin = sig["coin"]
    signal_type = sig["signal_type"].replace("_", " ")
    entry = format_price(sig["entry_price"])
    exit_p = format_price(sig["exit_price"])
    pnl = sig["pnl_pct"]
    duration = format_duration(sig["duration_minutes"])
    resolved_time = sig["outcome_time"]

    # Fetch stats
    coin_stats = database.get_coin_stats()
    signal_stats = database.get_signal_stats()

    coin_stat = next((c for c in coin_stats if c["coin"] == coin), None)
    sig_stat = next((s for s in signal_stats if s["signal_type"] == sig["signal_type"]), None)

    coin_line = ""
    if coin_stat:
        coin_line = f"📊 {coin} win rate  : {coin_stat['win_rate']:.1f}% ({coin_stat['wins']}W / {coin_stat['losses']}L)"

    sig_line = ""
    if sig_stat:
        sig_line = f"📊 {sig['signal_type'].replace('_', ' ')} rate   : {sig_stat['win_rate']:.1f}% ({sig_stat['wins']}W / {sig_stat['losses']}L)"

    if outcome == "WIN":
        header = "✅ SIGNAL RESOLVED — WIN"
        tp_line = f"🎯 Take Profit: {format_price(sig['take_profit'])}"
        return (
            f"{header}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 Coin       : {coin}\n"
            f"📣 Signal     : {signal_type}\n"
            f"💰 Entry      : {entry}\n"
            f"{tp_line}\n"
            f"📍 Exit Price : {exit_p}\n"
            f"💵 P&L        : +{pnl}%\n"
            f"⏳ Duration   : {duration}\n"
            f"🕐 Resolved   : {resolved_time}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{coin_line}\n"
            f"{sig_line}\n"
            f"⚠️ Not financial advice"
        )
    elif outcome == "LOSS":
        header = "❌ SIGNAL RESOLVED — LOSS"
        sl_line = f"🛑 Stop Loss  : {format_price(sig['stop_loss'])}"
        return (
            f"{header}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 Coin       : {coin}\n"
            f"📣 Signal     : {signal_type}\n"
            f"💰 Entry      : {entry}\n"
            f"{sl_line}\n"
            f"📍 Exit Price : {exit_p}\n"
            f"💵 P&L        : {pnl}%\n"
            f"⏳ Duration   : {duration}\n"
            f"🕐 Resolved   : {resolved_time}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{coin_line}\n"
            f"{sig_line}\n"
            f"⚠️ Not financial advice"
        )
    else:  # EXPIRED
        header = "⏳ SIGNAL EXPIRED — NO RESULT"
        return (
            f"{header}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🪙 Coin            : {coin}\n"
            f"📣 Signal          : {signal_type}\n"
            f"💰 Entry           : {entry}\n"
            f"📍 Price at expiry : {exit_p}\n"
            f"💵 Unrealized P&L  : {'+' if pnl >= 0 else ''}{pnl}%\n"
            f"⏳ Checked after   : {config.OUTCOME_CHECK_HOURS}h (timeout)\n"
            f"🕐 Expired         : {resolved_time}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ Not financial advice"
        )


def format_daily_summary() -> str:
    today_sigs = database.get_today_signals()
    total = len(today_sigs)
    wins = sum(1 for s in today_sigs if s["outcome"] == "WIN")
    losses = sum(1 for s in today_sigs if s["outcome"] == "LOSS")
    pending = sum(1 for s in today_sigs if s["outcome"] == "PENDING")
    expired = sum(1 for s in today_sigs if s["outcome"] == "EXPIRED")

    win_pct = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0

    today_str = datetime.utcnow().strftime("%d %b %Y")

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

async def send_message(text: str):
    """Send a message to the configured Telegram chat."""
    if not app or not app.bot:
        logger.error("Telegram bot not initialized")
        return
    try:
        await app.bot.send_message(
            chat_id=config.TELEGRAM_CHAT_ID,
            text=text,
        )
    except Exception as e:
        logger.error("Failed to send Telegram message: %s", e)


async def send_signal_alert(signal: Signal):
    await send_message(format_signal_alert(signal))


async def send_outcome(sig: dict):
    await send_message(format_outcome(sig))


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
        signal_time = datetime.strptime(s["signal_time"], "%Y-%m-%d %H:%M:%S")
        elapsed = int((datetime.utcnow() - signal_time).total_seconds() / 60)
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
            f"   {s['outcome_time']}\n\n"
        )
    msg += "⚠️ Not financial advice"
    await update.message.reply_text(msg)
