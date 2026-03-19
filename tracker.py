import logging
from datetime import datetime

import requests

import config
import database

logger = logging.getLogger(__name__)


def get_current_price(symbol: str) -> float | None:
    """Fetch current price from Binance."""
    for attempt in range(1, 4):
        try:
            resp = requests.get(
                config.BINANCE_PRICE_URL,
                params={"symbol": symbol},
                timeout=10,
            )
            resp.raise_for_status()
            return float(resp.json()["price"])
        except (requests.RequestException, ValueError, KeyError) as e:
            logger.warning("Price fetch attempt %d/3 for %s failed: %s", attempt, symbol, e)
            if attempt < 3:
                import time
                time.sleep(5)
    return None


def check_outcomes() -> list[dict]:
    """Check all pending signals against current prices. Returns resolved signals."""
    pending = database.get_pending_signals()
    resolved = []

    for sig in pending:
        price = get_current_price(sig["coin"])
        if price is None:
            logger.warning("Could not fetch price for %s — skipping outcome check", sig["coin"])
            continue

        signal_time = datetime.strptime(sig["signal_time"], "%Y-%m-%d %H:%M:%S")
        elapsed_minutes = int((datetime.utcnow() - signal_time).total_seconds() / 60)
        elapsed_hours = elapsed_minutes / 60

        outcome = None
        exit_price = price
        pnl_pct = 0.0

        if sig["signal_type"] == "STRONG_BUY":
            if price >= sig["take_profit"]:
                outcome = "WIN"
                exit_price = price
                pnl_pct = round((exit_price - sig["entry_price"]) / sig["entry_price"] * 100, 2)
            elif price <= sig["stop_loss"]:
                outcome = "LOSS"
                exit_price = price
                pnl_pct = round((exit_price - sig["entry_price"]) / sig["entry_price"] * 100, 2)
            elif elapsed_hours >= config.OUTCOME_CHECK_HOURS:
                outcome = "EXPIRED"
                pnl_pct = round((price - sig["entry_price"]) / sig["entry_price"] * 100, 2)

        elif sig["signal_type"] == "STRONG_SELL":
            if price <= sig["take_profit"]:
                outcome = "WIN"
                exit_price = price
                pnl_pct = round((sig["entry_price"] - exit_price) / sig["entry_price"] * 100, 2)
            elif price >= sig["stop_loss"]:
                outcome = "LOSS"
                exit_price = price
                pnl_pct = round((sig["entry_price"] - exit_price) / sig["entry_price"] * 100, 2)
            elif elapsed_hours >= config.OUTCOME_CHECK_HOURS:
                outcome = "EXPIRED"
                pnl_pct = round((sig["entry_price"] - price) / sig["entry_price"] * 100, 2)

        if outcome:
            database.resolve_signal(
                signal_id=sig["id"],
                outcome=outcome,
                exit_price=exit_price,
                pnl_pct=pnl_pct,
                duration_minutes=elapsed_minutes,
            )
            logger.info("%s signal #%d for %s resolved as %s (P&L: %.2f%%)",
                        sig["signal_type"], sig["id"], sig["coin"], outcome, pnl_pct)

            resolved_sig = database.get_signal_by_id(sig["id"])
            resolved.append(resolved_sig)

    return resolved
