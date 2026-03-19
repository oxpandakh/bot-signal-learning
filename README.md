# Crypto Trading Signal Bot

A Python bot that scans 10 crypto pairs on Binance every 15 minutes, generates **STRONG BUY / STRONG SELL** signals using multi-timeframe confluence, tracks outcomes, and delivers everything via Telegram.

## Technical Indicators Used

- RSI (14) — oversold/overbought detection
- MACD (12, 26, 9) — crossover detection
- Bollinger Bands (20)
- EMA 20 / 50 / 200
- Volume ratio (vs 20-period average)
- Stochastic RSI

Signals require **confluence** — both 15m and 1H timeframes must agree.

## Prerequisites

- Python 3.10+
- A Telegram bot token
- A Telegram chat ID

## Setup

### 1. Create a Telegram Bot

1. Open Telegram and search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** (looks like `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)

### 2. Get Your Telegram Chat ID

1. Search for **@userinfobot** on Telegram
2. Send `/start` — it will reply with your **chat ID** (a number like `123456789`)
3. Alternatively, add your bot to a group and use `@raw_data_bot` to find the group chat ID

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
TAKE_PROFIT_PCT=3.0       # Take profit percentage
STOP_LOSS_PCT=1.5         # Stop loss percentage
OUTCOME_CHECK_HOURS=4     # Hours before signal expires
SCAN_INTERVAL_MINUTES=15  # Scan frequency
COINS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,ADAUSDT,AVAXUSDT,DOGEUSDT,DOTUSDT,MATICUSDT
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

## Signal Logic

### STRONG BUY (all must be true)
- RSI < 35 on **both** 15m and 1H
- MACD bullish crossover on 1H
- Price above EMA 50
- Volume > 150% of 20-period average

### STRONG SELL (all must be true)
- RSI > 70 on **both** 15m and 1H
- MACD bearish crossover on 1H
- Price below EMA 50
- Volume > 150% of 20-period average

### Win Rate Tracking

Each signal is tracked until resolution:

- **WIN** — Price reaches the take profit level (default +3%)
- **LOSS** — Price reaches the stop loss level (default -1.5%)
- **EXPIRED** — Neither TP nor SL hit within the timeout (default 4 hours)

Win rate = Wins / (Wins + Losses). Expired signals are excluded from win rate calculation.

Outcomes are checked every 15 minutes. When a signal resolves, a result message is sent to Telegram immediately with the P&L and updated win rate stats.

## Project Structure

```
├── main.py           # Entry point — starts scheduler + Telegram bot
├── config.py         # Loads .env and exposes constants
├── scanner.py        # Fetches OHLCV data from Binance
├── analyzer.py       # Computes technical indicators via pandas-ta
├── signals.py        # Signal generation logic (STRONG BUY/SELL)
├── tracker.py        # Outcome tracking (WIN/LOSS/EXPIRED)
├── telegram_bot.py   # Telegram message formatting + command handlers
├── scheduler.py      # APScheduler job configuration
├── database.py       # SQLite database operations
├── .env.example      # Environment variable template
├── requirements.txt  # Python dependencies
└── signals.db        # SQLite database (created on first run)
```

## Data Source

All market data comes from the [Binance public REST API](https://binance-docs.github.io/apidocs/spot/en/#kline-candlestick-data) — no API key required.

## Disclaimer

This bot is for educational purposes only. It is **not financial advice**. Trading cryptocurrency involves significant risk. Always do your own research before making trading decisions.
# bot-signal-learning
