import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

import config
import scanner
import analyzer
import signals
import tracker
import telegram_bot

logger = logging.getLogger(__name__)


async def scan_and_signal():
    """Run full scan → analyze → generate signals → send alerts."""
    logger.info("Starting scan cycle...")
    try:
        market_data = await asyncio.to_thread(scanner.scan_all_coins)

        if not market_data:
            logger.warning("No market data received — skipping this cycle")
            return

        analysis = analyzer.analyze_all(market_data)
        fired = signals.generate_signals(analysis)

        for sig, signal_id in fired:
            await telegram_bot.send_signal_alert(sig, signal_id)

        logger.info("Scan cycle complete — %d signal(s) fired", len(fired))

    except Exception as e:
        logger.error("Error during scan cycle: %s", e, exc_info=True)


async def check_and_resolve():
    """Check pending signal outcomes and send results."""
    logger.info("Checking pending signal outcomes...")
    try:
        resolved = await asyncio.to_thread(tracker.check_outcomes)

        for sig in resolved:
            await telegram_bot.send_outcome(sig)

        logger.info("Outcome check complete — %d signal(s) resolved", len(resolved))

    except Exception as e:
        logger.error("Error during outcome check: %s", e, exc_info=True)


async def daily_report():
    """Send daily summary report."""
    logger.info("Sending daily summary report...")
    try:
        await telegram_bot.send_daily_summary()
        logger.info("Daily summary sent")
    except Exception as e:
        logger.error("Error sending daily summary: %s", e, exc_info=True)


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler."""
    sched = AsyncIOScheduler()

    # Scan + signal generation every N minutes
    sched.add_job(
        scan_and_signal,
        trigger=IntervalTrigger(minutes=config.SCAN_INTERVAL_MINUTES),
        id="scan_and_signal",
        name="Scan & Signal",
        max_instances=1,
        replace_existing=True,
    )

    # Outcome checker every 15 minutes
    sched.add_job(
        check_and_resolve,
        trigger=IntervalTrigger(minutes=15),
        id="check_outcomes",
        name="Outcome Checker",
        max_instances=1,
        replace_existing=True,
    )

    # Daily summary at 00:00 UTC
    sched.add_job(
        daily_report,
        trigger=CronTrigger(hour=0, minute=0),
        id="daily_report",
        name="Daily Report",
        max_instances=1,
        replace_existing=True,
    )

    return sched
