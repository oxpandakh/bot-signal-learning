# Crypto Trading Signal Bot

A Python bot that scans **36 crypto pairs** on Binance every 15 minutes, generates **STRONG BUY / STRONG SELL** signals with a **strength percentage** (40%–100%), tracks outcomes, and delivers everything via Telegram.

## Features

- Multi-timeframe analysis (15m + 1H confluence)
- Signal strength scoring (40%–100%) with visual bar
- Win rate tracking with auto-resolution (TP/SL/Expiry)
- Telegram alerts with detailed indicator data
- Daily performance reports
- Railway deployment ready (SQLite + Volume persistence)

## Technical Indicators

- **RSI (14)** — oversold/overbought detection
- **MACD (12, 26, 9)** — crossover detection
- **Bollinger Bands (20)**
- **EMA 20 / 50 / 200**
- **Volume ratio** (vs 20-period average)
- **Stochastic RSI**

## Signal Strength Scoring

Signals are scored from 0–100% based on how strongly each condition is met. Only signals with **>= 40% strength** are sent.

| Component | Max Points | How Scored |
|-----------|-----------|------------|
| RSI 15m | 20 pts | Graded: deeper oversold/overbought = more points |
| RSI 1H | 20 pts | Same grading |
| MACD | 25 pts | Crossover confirmed = 25, else 0 |
| EMA 50 | 15 pts | Price on correct side = 15, else 0 |
| Volume | 20 pts | Graded: higher volume = more points |

| Strength | Label |
|----------|-------|
| 90–100% | 🔥 EXTREME |
| 80–89% | 💪 VERY STRONG |
| 70–79% | ✅ STRONG |
| 60–69% | ⚡ MODERATE |
| 50–59% | 📊 FAIR |
| 40–49% | ⚠️ WEAK |

## Supported Coins (36 pairs)

BTC, ETH, SOL, BNB, XRP, ADA, AVAX, DOGE, DOT, POL, SUI, NEAR, ASTR, LINK, TON, OP, APT, ARB, INJ, TIA, SEI, JUP, PEPE, FET, RENDER, ONDO, STX, IMX, ATOM, FIL, FTM, RUNE, AAVE, ENA, WLD, PENDLE

## Prerequisites

- Python 3.10+
- A Telegram bot token
- A Telegram chat ID (personal or channel)

## Setup

### 1. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** (looks like `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)

### 2. Get Your Telegram Chat ID

**For personal chat:**
1. Search for **@userinfobot** on Telegram
2. Send `/start` — it replies with your numeric ID

**For a channel (recommended):**
1. Create a channel and add your bot as **admin** (with "Post Messages" permission)
2. Forward a message from the channel to **@userinfobot** to get the channel ID (starts with `-100`)

### 3. Install Dependencies

```bash
git clone <your-repo-url>
cd bot-signal-learning
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your values:

```
TELEGRAM_BOT_TOKEN=your_actual_bot_token
TELEGRAM_CHAT_ID=your_actual_chat_id
```

Optional settings (defaults shown):
```
TAKE_PROFIT_PCT=3.0           # Take profit percentage
STOP_LOSS_PCT=1.5             # Stop loss percentage
OUTCOME_CHECK_HOURS=4         # Hours before signal expires
SCAN_INTERVAL_MINUTES=15      # Scan frequency
BINANCE_BASE_URL=https://api.binance.com  # Change if region-blocked
COINS=BTCUSDT,ETHUSDT,...     # Comma-separated coin list
```

### 5. Run the Bot

```bash
python main.py
```

The bot will:
1. Send a startup message to your Telegram
2. Run an initial scan immediately
3. Continue scanning every 15 minutes
4. Check signal outcomes every 15 minutes
5. Send a daily summary at 00:00 UTC

## Deploy on Railway

1. Push repo to GitHub
2. Create a new project on [Railway](https://railway.app) and connect your repo
3. Set environment variables in Railway dashboard (same as `.env`)
4. **Change region** to Europe or Asia if Binance returns HTTP 451 (US blocked)
5. Add a **Volume** (Settings → Volumes → Mount path: `/data`) for SQLite persistence
6. Railway auto-detects `Procfile` and runs as a worker

> **Note:** Without a Volume, your database resets on each deploy. The bot auto-saves to `/data/signals.db` when `RAILWAY_VOLUME_MOUNT_PATH` is set.

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and bot description |
| `/winrate` | All-time win rate by signal type and coin |
| `/stats` | Today's performance summary |
| `/best` | Top 3 coins by win rate (min 3 signals) |
| `/worst` | Bottom 3 coins by win rate (min 3 signals) |
| `/pending` | List all open/unresolved signals |
| `/history N` | Last N resolved signals (default 5) |

## Telegram Messages

### Signal Alert
```
🚀 STRONG BUY — SOLUSDT
━━━━━━━━━━━━━━━━━━━━
📶 Strength   : 85% 💪 VERY STRONG
   ████████░░
💰 Entry Price : $134.20
🎯 Take Profit : $138.23  (+3%)
🛑 Stop Loss   : $132.12  (-1.5%)
📊 RSI 15m     : 31.2
📊 RSI 1H      : 32.8
📈 MACD        : Bullish crossover
📦 Volume      : +210% above avg
⏱ Confluence  : 15m + 1H
🕐 Time        : 19 Mar 2026 12:00 UTC
━━━━━━━━━━━━━━━━━━━━
⚠️ Not financial advice
```

### Signal Result (WIN / LOSS / EXPIRED)
Sent automatically when a signal resolves — includes P&L, duration, and updated win rate stats.

### Daily Summary
Sent at 00:00 UTC with total signals, win/loss breakdown by type and coin, best/worst performers, and all-time win rate.

## Win Rate Tracking

Each signal is tracked until resolution:

- **WIN** — Price reaches the take profit level (default +3%)
- **LOSS** — Price reaches the stop loss level (default -1.5%)
- **EXPIRED** — Neither TP nor SL hit within the timeout (default 4 hours)

Win rate = Wins / (Wins + Losses). Expired signals are excluded from win rate calculation.

Outcomes are checked every 15 minutes. When a signal resolves, a result message is sent to Telegram immediately.

## Project Structure

```
├── main.py           # Entry point — starts scheduler + Telegram bot
├── config.py         # Loads .env and exposes constants
├── scanner.py        # Fetches OHLCV data from Binance
├── analyzer.py       # Computes technical indicators (ta library)
├── signals.py        # Signal strength scoring + generation logic
├── tracker.py        # Outcome tracking (WIN/LOSS/EXPIRED)
├── telegram_bot.py   # Telegram message formatting + command handlers
├── scheduler.py      # APScheduler job configuration
├── database.py       # SQLite database operations
├── .env.example      # Environment variable template
├── requirements.txt  # Python dependencies
├── Procfile          # Railway deployment config
├── runtime.txt       # Python version for Railway
└── signals.db        # SQLite database (created on first run)
```

## Data Source

All market data comes from the [Binance public REST API](https://binance-docs.github.io/apidocs/spot/en/#kline-candlestick-data) — no API key required. Uses 250 candles per request to support EMA 200 calculation.

## Disclaimer

This bot is for educational purposes only. It is **not financial advice**. Trading cryptocurrency involves significant risk. Always do your own research before making trading decisions.
