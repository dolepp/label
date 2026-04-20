#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""Compatibility entrypoint for the current monolithic bot.

The project is being migrated from label.py to modules gradually. Until a
feature is fully moved and verified, startup must go through the legacy module
without exec(), so __name__ guards inside label.py keep their normal behavior.
"""
import logging
import os
import sys


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def configure_telegram_timeouts() -> None:
    try:
        import telebot.apihelper

        telebot.apihelper.READ_TIMEOUT = 30
        telebot.apihelper.CONNECT_TIMEOUT = 10
    except Exception as exc:
        logger.warning("Could not configure Telegram API timeouts: %s", exc)


def start_bot() -> None:
    import label

    configure_telegram_timeouts()
    try:
        from handlers import register_optional_handlers

        register_optional_handlers(label.bot)
    except Exception as exc:
        logger.error("Could not register optional modular handlers: %s", exc)
        raise

    if hasattr(label, "start_bot_with_retry"):
        label.start_bot_with_retry()
        return

    label.bot.polling(
        none_stop=True,
        interval=0,
        timeout=20,
        long_polling_timeout=25,
        skip_pending=True,
    )


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("TWAS Label Bot - legacy-compatible launcher")
    logger.info("=" * 50)
    start_bot()
