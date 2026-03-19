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

Railway is a cloud platform that can run your bot 24/7. You need the **Pro plan** ($5/month) to use Volumes for database persistence.

### Step 1: Push to GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/bot-signal-learning.git
git push -u origin main
```

> **Important:** Make sure `.env` is in your `.gitignore` so you don't push your bot token to GitHub.

### Step 2: Create Railway Project

1. Go to [railway.app](https://railway.app) and sign in with GitHub
2. Click **"New Project"**
3. Select **"Deploy from GitHub Repo"**
4. Choose your `bot-signal-learning` repository
5. Railway will auto-detect the `Procfile` and start deploying

### Step 3: Set Environment Variables

1. Click on your **service** (the box in your project canvas)
2. Go to the **"Variables"** tab
3. Click **"Raw Editor"** and paste all your variables:

```
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
TAKE_PROFIT_PCT=3.0
STOP_LOSS_PCT=1.5
OUTCOME_CHECK_HOURS=4
SCAN_INTERVAL_MINUTES=15
BINANCE_BASE_URL=https://api.binance.com
COINS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,ADAUSDT,AVAXUSDT,DOGEUSDT,DOTUSDT,POLUSDT,SUIUSDT,NEARUSDT,ASTRUSDT,LINKUSDT,TONUSDT,OPUSDT,APTUSDT,ARBUSDT,INJUSDT,TIAUSDT,SEIUSDT,JUPUSDT,PEPEUSDT,FETUSDT,RENDERUSDT,ONDOUSDT,STXUSDT,IMXUSDT,ATOMUSDT,FILUSDT,FTMUSDT,RUNEUSDT,AAVEUSDT,ENAUSDT,WLDUSDT,PENDLEUSDT
```

4. Click **"Update Variables"** — Railway will redeploy automatically

### Step 4: Change Region (Important!)

Binance blocks US-based servers (HTTP 451 error). You must change the deployment region:

1. Click on your **service**
2. Go to **"Settings"** tab
3. Scroll to **"Region"**
4. Select **"Europe (West)"** or **"Asia (Southeast)"**
5. Railway will redeploy in the new region

### Step 5: Add a Volume (Pro plan required)

Without a Volume, your SQLite database resets on every deploy. To persist data:

1. Click on your **service**
2. Go to **"Settings"** tab → scroll to **"Volumes"**
3. Click **"Add Volume"**
4. Set Mount Path: `/data`
5. Click **"Add"**

Railway automatically sets `RAILWAY_VOLUME_MOUNT_PATH=/data`, and the bot saves the database at `/data/signals.db`.

### Step 6: Disable Public Networking

The bot doesn't need a web port — it only polls Telegram:

1. Click on your **service**
2. Go to **"Settings"** tab → **"Networking"**
3. Remove any public domain or port if assigned

### Step 7: Verify Deployment

1. Go to the **"Deployments"** tab to see build logs
2. You should see logs like:
   ```
   Database initialized
   Starting Telegram bot polling...
   📡 [1/36] Fetching BTCUSDT ...
   ```
3. Check your Telegram — you should receive the startup message:
   ```
   🤖 Crypto Signal Bot started! Scanning BTCUSDT, ETHUSDT, SOLUSDT... every 15 minutes.
   ```

### Troubleshooting

| Problem | Solution |
|---------|----------|
| HTTP 451 from Binance | Change Railway region to Europe or Asia |
| `Conflict: terminated by other getUpdates` | Stop your local bot — only one instance can run per token |
| Database resets on deploy | Add a Volume (Step 5) |
| Bot not starting | Check "Deployments" tab for error logs |
| No signals firing | Normal — signals only fire when strength >= 40% |

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

## Built With — Vibe Coding with Claude Code

This entire project was **vibe coded** using [Claude Code](https://claude.com/claude-code) — Anthropic's AI coding assistant in the terminal. No boilerplate was written manually.

### What is Vibe Coding?

Vibe coding is a development style where you describe **what** you want in natural language, and an AI assistant writes the code for you. You guide the direction, review the output, and iterate — like pair programming with AI.

### How This Project Was Built

1. **Single prompt** — Started with a detailed specification describing all features, signal logic, database schema, and Telegram message formats
2. **Iterative refinement** — Each feature was refined through conversation:
   - "add more coins" → added 20 new trading pairs
   - "signal send with Strong percent start from 60%" → built the strength scoring system
   - "now update send with 40%" → lowered threshold
   - "SIGNAL RESOLVED can send with reply on signal message?" → added Telegram reply threading
   - "remove proxy" → cleaned up unused code
3. **Deploy assistance** — Railway deployment was configured through conversation, including region selection, volume setup, and troubleshooting HTTP 451 errors

### Development Tools

- [Claude Code](https://claude.com/claude-code) — AI coding assistant
- [VS Code](https://code.visualstudio.com/) — IDE
- [Railway](https://railway.app/) — Cloud hosting
- [GitHub](https://github.com/) — Version control

### Development Timeline

This project went from zero to deployed in a **single conversation session** with Claude Code — including:
- Full project scaffolding (12 files)
- Technical indicator calculations
- Signal strength scoring algorithm
- Telegram bot with 7 commands
- Win rate tracking with auto-resolution
- Railway deployment configuration
- Iterative feature additions and bug fixes

### Reproduce This Yourself

1. Install [Claude Code](https://claude.com/claude-code)
2. Open a terminal in an empty folder
3. Paste the project specification as your first prompt
4. Iterate: test, find issues, describe fixes in natural language
5. Deploy with: "deploy this on Railway"

> **Tip:** The more detailed your initial specification, the better the first output. Include database schemas, message formats, and edge cases upfront.

### Example Prompts Used

**Prompt 1 — Initial build:**
```
Build a crypto signal bot. Scan Binance coins every 15 minutes,
use RSI + MACD + EMA + Volume to find buy/sell signals,
send alerts to Telegram, track win rate with TP/SL,
store everything in SQLite.
```

**Prompt 2 — Add signal strength:**
```
Add a strength percentage to signals. Score each indicator
(RSI, MACD, EMA, Volume) and show a % from 0-100.
Only send signals when strength >= 60%.
Show a progress bar and label (EXTREME, VERY STRONG, STRONG, MODERATE) in the Telegram message.
```

**Prompt 3 — Lower threshold and add more levels:**
```
Lower the minimum signal strength to 40%.
Add new labels: FAIR for 50-59% and WEAK for 40-49%.
Make the Telegram title match the strength level instead of always saying STRONG BUY.
```

**Prompt 4 — Fix title mismatch:**
```
🚀 STRONG BUY — FETUSDT
📶 Strength : 50% 📊 FAIR
title why write STRONG BUY?
```

**Prompt 5 — Add reply threading:**
```
SIGNAL RESOLVED can send with reply on signal message?
```

**Prompt 6 — Add coins:**
```
add more 20 coin
```

**Prompt 7 — Fix errors:**
```
<paste the error log>
```

> **Key takeaway:** You don't need perfect English or long prompts. Short, direct instructions work. Claude Code understands context from the conversation and codebase.

## Data Source

All market data comes from the [Binance public REST API](https://binance-docs.github.io/apidocs/spot/en/#kline-candlestick-data) — no API key required. Uses 250 candles per request to support EMA 200 calculation.

## Disclaimer

This bot is for educational purposes only. It is **not financial advice**. Trading cryptocurrency involves significant risk. Always do your own research before making trading decisions.
