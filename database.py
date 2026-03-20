import sqlite3
from datetime import datetime
from typing import Optional

import config


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            coin TEXT NOT NULL,
            signal_type TEXT NOT NULL,
            entry_price REAL NOT NULL,
            take_profit REAL NOT NULL,
            stop_loss REAL NOT NULL,
            rsi_15m REAL,
            rsi_1h REAL,
            macd_cross TEXT,
            volume_ratio REAL,
            ema_position TEXT,
            signal_time DATETIME NOT NULL,
            outcome TEXT DEFAULT 'PENDING',
            outcome_time DATETIME,
            exit_price REAL,
            pnl_pct REAL,
            duration_minutes INTEGER,
            telegram_message_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS coin_stats (
            coin TEXT PRIMARY KEY,
            total INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            expired INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0.0
        );

        CREATE TABLE IF NOT EXISTS signal_stats (
            signal_type TEXT PRIMARY KEY,
            total INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            expired INTEGER DEFAULT 0,
            win_rate REAL DEFAULT 0.0
        );
    """)
    conn.commit()

    # Migration: add telegram_message_id if missing (existing DBs won't have it)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(signals)").fetchall()}
    if "telegram_message_id" not in existing:
        conn.execute("ALTER TABLE signals ADD COLUMN telegram_message_id INTEGER")
        conn.commit()

    conn.close()


def insert_signal(coin: str, signal_type: str, entry_price: float,
                  take_profit: float, stop_loss: float, rsi_15m: float,
                  rsi_1h: float, macd_cross: str, volume_ratio: float,
                  ema_position: str) -> int:
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO signals
           (coin, signal_type, entry_price, take_profit, stop_loss,
            rsi_15m, rsi_1h, macd_cross, volume_ratio, ema_position, signal_time)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (coin, signal_type, entry_price, take_profit, stop_loss,
         rsi_15m, rsi_1h, macd_cross, volume_ratio, ema_position,
         datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    )
    signal_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return signal_id


def set_telegram_message_id(signal_id: int, message_id: int):
    conn = get_connection()
    conn.execute(
        "UPDATE signals SET telegram_message_id=? WHERE id=?",
        (message_id, signal_id)
    )
    conn.commit()
    conn.close()


def has_pending_signal(coin: str, signal_type: str) -> bool:
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM signals WHERE coin=? AND signal_type=? AND outcome='PENDING'",
        (coin, signal_type)
    ).fetchone()
    conn.close()
    return row["cnt"] > 0


def get_pending_signals() -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM signals WHERE outcome='PENDING'"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resolve_signal(signal_id: int, outcome: str, exit_price: float,
                   pnl_pct: float, duration_minutes: int):
    conn = get_connection()
    conn.execute(
        """UPDATE signals SET outcome=?, outcome_time=?, exit_price=?,
           pnl_pct=?, duration_minutes=? WHERE id=?""",
        (outcome, datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
         exit_price, pnl_pct, duration_minutes, signal_id)
    )
    conn.commit()
    conn.close()

    signal = get_signal_by_id(signal_id)
    if signal:
        _update_stats(signal["coin"], signal["signal_type"])


def get_signal_by_id(signal_id: int) -> Optional[dict]:
    conn = get_connection()
    row = conn.execute("SELECT * FROM signals WHERE id=?", (signal_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def _update_stats(coin: str, signal_type: str):
    conn = get_connection()

    # Update coin_stats
    row = conn.execute(
        """SELECT COUNT(*) as total,
           SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as wins,
           SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses,
           SUM(CASE WHEN outcome='EXPIRED' THEN 1 ELSE 0 END) as expired
           FROM signals WHERE coin=? AND outcome!='PENDING'""",
        (coin,)
    ).fetchone()
    total = row["total"] or 0
    wins = row["wins"] or 0
    losses = row["losses"] or 0
    expired = row["expired"] or 0
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0
    conn.execute(
        """INSERT INTO coin_stats (coin, total, wins, losses, expired, win_rate)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(coin) DO UPDATE SET
           total=?, wins=?, losses=?, expired=?, win_rate=?""",
        (coin, total, wins, losses, expired, win_rate,
         total, wins, losses, expired, win_rate)
    )

    # Update signal_stats
    row = conn.execute(
        """SELECT COUNT(*) as total,
           SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as wins,
           SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses,
           SUM(CASE WHEN outcome='EXPIRED' THEN 1 ELSE 0 END) as expired
           FROM signals WHERE signal_type=? AND outcome!='PENDING'""",
        (signal_type,)
    ).fetchone()
    total = row["total"] or 0
    wins = row["wins"] or 0
    losses = row["losses"] or 0
    expired = row["expired"] or 0
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0
    conn.execute(
        """INSERT INTO signal_stats (signal_type, total, wins, losses, expired, win_rate)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(signal_type) DO UPDATE SET
           total=?, wins=?, losses=?, expired=?, win_rate=?""",
        (signal_type, total, wins, losses, expired, win_rate,
         total, wins, losses, expired, win_rate)
    )

    conn.commit()
    conn.close()


def get_coin_stats() -> list:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM coin_stats ORDER BY win_rate DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_signal_stats() -> list:
    conn = get_connection()
    rows = conn.execute("SELECT * FROM signal_stats").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_today_signals() -> list:
    conn = get_connection()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT * FROM signals WHERE date(signal_time)=?", (today,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_last_resolved(limit: int = 5) -> list:
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM signals WHERE outcome!='PENDING'
           ORDER BY outcome_time DESC LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_best_coins(limit: int = 3) -> list:
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM coin_stats WHERE (wins + losses) >= 3
           ORDER BY win_rate DESC LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_worst_coins(limit: int = 3) -> list:
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM coin_stats WHERE (wins + losses) >= 3
           ORDER BY win_rate ASC LIMIT ?""",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_alltime_win_rate() -> float:
    conn = get_connection()
    row = conn.execute(
        """SELECT
           SUM(CASE WHEN outcome='WIN' THEN 1 ELSE 0 END) as wins,
           SUM(CASE WHEN outcome='LOSS' THEN 1 ELSE 0 END) as losses
           FROM signals WHERE outcome!='PENDING'"""
    ).fetchone()
    conn.close()
    wins = row["wins"] or 0
    losses = row["losses"] or 0
    return (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0.0
