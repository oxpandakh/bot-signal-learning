import asyncio
import logging
import sys

import colorlog

import config
import database
import telegram_bot
import scheduler


def setup_logging():
    """Configure colorlog for console output."""
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold_red",
        },
    ))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


async def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    # Validate config
    if not config.TELEGRAM_BOT_TOKEN or config.TELEGRAM_BOT_TOKEN == "your_bot_token_here":
        logger.error("TELEGRAM_BOT_TOKEN not set. Copy .env.example to .env and fill in your values.")
        sys.exit(1)
    if not config.TELEGRAM_CHAT_ID or config.TELEGRAM_CHAT_ID == "your_chat_id_here":
        logger.error("TELEGRAM_CHAT_ID not set. Copy .env.example to .env and fill in your values.")
        sys.exit(1)

    # Init database
    database.init_db()
    logger.info("Database initialized")

    # Build Telegram bot
    tg_app = telegram_bot.build_app()

    # Initialize the bot (needed for sending messages before polling starts)
    await tg_app.initialize()

    # Send startup message
    await telegram_bot.send_startup_message()
    logger.info("Startup message sent to Telegram")

    # Create and start scheduler
    sched = scheduler.create_scheduler()
    sched.start()
    logger.info("Scheduler started — scanning every %d minutes", config.SCAN_INTERVAL_MINUTES)

    # Run initial scan immediately
    await scheduler.scan_and_signal()

    # Start Telegram polling (this blocks until stopped)
    logger.info("Starting Telegram bot polling...")
    try:
        await tg_app.start()
        await tg_app.updater.start_polling(drop_pending_updates=True)

        # Keep running until interrupted
        stop_event = asyncio.Event()
        try:
            await stop_event.wait()
        except (KeyboardInterrupt, SystemExit):
            pass
    finally:
        logger.info("Shutting down...")
        sched.shutdown(wait=False)
        await tg_app.updater.stop()
        await tg_app.stop()
        await tg_app.shutdown()
        logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
