#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""Модульный запуск бота: обработчики в handlers/ (start, profile, releases, distribution, finance, support, admin, reviews, services)."""
import sys
import os
import logging
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot_modular.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

from core.bot import bot

logger.info("🤖 Модульный бот инициализирован")

# Пул БД
from utils.database import init_db_pool

if init_db_pool() is False:
    logger.error("❌ Ошибка инициализации БД")
    sys.exit(1)
logger.info("✅ База данных инициализирована")

# Все обработчики из handlers/*.py (регистрируются на core.bot при импорте)
logger.info("📝 Загрузка обработчиков из handlers/...")
import handlers.common  # noqa: E402 — общие хелперы и константы
import handlers.start  # noqa: E402
import handlers.profile  # noqa: E402
import handlers.releases  # noqa: E402
import handlers.distribution  # noqa: E402
import handlers.finance  # noqa: E402
import handlers.support  # noqa: E402
import handlers.admin  # noqa: E402
import handlers.reviews  # noqa: E402
import handlers.services  # noqa: E402

logger.info("✅ Обработчики загружены")

# Инициализация схемы БД (функции из handlers.common)
logger.info("🔧 Инициализация БД и таблиц...")
try:
    handlers.common.init_database()
    logger.info("✅ init_database выполнен")
except Exception as e:
    logger.error(f"❌ init_database: {e}")
try:
    handlers.common.ensure_label_columns()
    logger.info("✅ ensure_label_columns выполнен")
except Exception as e:
    logger.error(f"❌ ensure_label_columns: {e}")
try:
    handlers.common.add_platform_links_column()
    logger.info("✅ add_platform_links_column выполнен")
except Exception as e:
    logger.error(f"❌ add_platform_links_column: {e}")
try:
    handlers.common.create_referrals_table()
    logger.info("✅ create_referrals_table выполнен")
except Exception as e:
    logger.error(f"❌ create_referrals_table: {e}")

# Проверка бота и канала
logger.info("🔧 Проверка бота и канала...")
try:
    bot_info = bot.get_me()
    logger.info(f"✅ Бот подключён: @{bot_info.username}")
    if not handlers.common.check_bot_instance():
        logger.error("❌ Обнаружен конфликт экземпляров бота")
        sys.exit(1)
except Exception as e:
    logger.error(f"❌ Ошибка проверки бота: {e}")
    sys.exit(1)

if not handlers.common.test_channel_access():
    logger.error("❌ Нет доступа к каналу. Добавьте бота в канал как администратора.")
    sys.exit(1)
logger.info("✅ Доступ к каналу проверен")


def start_bot():
    """Запуск polling с переподключением при ошибках."""
    retry_delay = 5
    consecutive_errors = 0
    max_consecutive_errors = 5
    try:
        import telebot.apihelper
        telebot.apihelper.READ_TIMEOUT = 30
        telebot.apihelper.CONNECT_TIMEOUT = 10
        logger.info("✅ Таймауты API настроены")
    except Exception as e:
        logger.warning(f"⚠️ Таймауты API: {e}")

    while True:
        try:
            logger.info("🤖 Запуск polling...")
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
            logger.info("🛑 Остановка пользователем")
            break
        except Exception as e:
            err_str = str(e).lower()
            consecutive_errors += 1
            logger.error(f"❌ Ошибка: {e}")
            if "409" in err_str or "conflict" in err_str:
                logger.error("🚨 Запущен другой экземпляр бота с тем же токеном")
                time.sleep(10)
            else:
                time.sleep(retry_delay)
            if consecutive_errors >= max_consecutive_errors:
                retry_delay = min(retry_delay * 2, 120)
                consecutive_errors = 0
            logger.info(f"🔄 Повтор через {retry_delay} с...")
            time.sleep(retry_delay)


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("TWAS Label Bot — Модульная версия (handlers/)")
    logger.info("=" * 50)
    start_bot()
