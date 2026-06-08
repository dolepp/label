"""Telegram polling runner detached from the legacy monolith."""
from __future__ import annotations

import logging
import time
from typing import Callable

import telebot.apihelper

logger = logging.getLogger(__name__)
connection_logger = logging.getLogger("connection")


def configure_telegram_timeouts(read_timeout: int = 30, connect_timeout: int = 10) -> None:
    try:
        telebot.apihelper.READ_TIMEOUT = read_timeout
        telebot.apihelper.CONNECT_TIMEOUT = connect_timeout
        logger.info("✅ Таймауты API настроены: READ=%ss, CONNECT=%ss", read_timeout, connect_timeout)
    except Exception as exc:
        logger.warning("⚠️ Не удалось настроить таймауты API: %s", exc)


def check_bot_instance(bot) -> bool:
    try:
        bot_info = bot.get_me()
        logger.info("✅ Bot instance check passed: @%s", bot_info.username)
        return True
    except telebot.apihelper.ApiTelegramException as exc:
        if "409" in str(exc) or "Conflict" in str(exc):
            logger.error("🚨 CRITICAL: Another bot instance is already running!")
            logger.error("🛑 Please stop all other bot instances before starting this one")
            return False
        logger.error("❌ Bot instance check failed: %s", exc)
        return False
    except Exception as exc:
        logger.error("❌ Unexpected error during bot check: %s", exc)
        return False


def start_bot_with_retry(bot, get_connection: Callable | None = None, return_connection: Callable | None = None) -> None:
    retry_delay = 5
    consecutive_errors = 0
    max_consecutive_errors = 5
    configure_telegram_timeouts()

    while True:
        try:
            logger.info("🤖 Starting Telegram bot...")
            consecutive_errors = 0
            retry_delay = 5
            bot.polling(
                none_stop=True,
                interval=0,
                timeout=20,
                long_polling_timeout=25,
                skip_pending=True,
            )
        except KeyboardInterrupt:
            logger.info("🛑 Bot stopped by user")
            break
        except telebot.apihelper.ApiTelegramException as api_error:
            logger.error("❌ Telegram API error: %s", api_error)
            connection_logger.error("API Error: %s", api_error)
            consecutive_errors += 1
            error_str = str(api_error).lower()
            if "timeout" in error_str or "read timed out" in error_str:
                logger.warning("⏱️ API timeout detected, retrying...")
                time.sleep(3)
            elif "connection reset" in error_str or "connection aborted" in error_str:
                logger.warning("🔄 Connection reset detected, retrying...")
                time.sleep(2)
            elif "too many requests" in error_str or "429" in error_str:
                logger.warning("⏳ Rate limit exceeded, waiting longer...")
                time.sleep(30)
            elif "409" in error_str or "conflict" in error_str:
                logger.error("🚨 CRITICAL: Multiple bot instances detected!")
                time.sleep(10)
            else:
                time.sleep(retry_delay)
        except (ConnectionError, TimeoutError) as exc:
            logger.error("❌ Connection/timeout error: %s", exc)
            connection_logger.error("Connection/timeout error: %s", exc)
            consecutive_errors += 1
            time.sleep(3 if isinstance(exc, TimeoutError) else retry_delay)
        except Exception as exc:
            error_str = str(exc).lower()
            logger.error("❌ Unexpected error: %s", exc)
            consecutive_errors += 1
            time.sleep(3 if "timeout" in error_str or "timed out" in error_str else retry_delay)

        if consecutive_errors >= max_consecutive_errors:
            logger.warning("⚠️ Too many consecutive errors (%s), increasing delay...", consecutive_errors)
            retry_delay = min(retry_delay * 2, 120)
            consecutive_errors = 0

        logger.error("🔄 Retrying in %s seconds...", retry_delay)
        time.sleep(retry_delay)

        if get_connection and return_connection:
            conn = None
            try:
                conn = get_connection()
                if conn:
                    logger.info("✅ Database connection OK")
                else:
                    logger.error("❌ Database connection failed")
            except Exception as db_error:
                logger.error("❌ Database error: %s", db_error)
            finally:
                if conn:
                    return_connection(conn)
