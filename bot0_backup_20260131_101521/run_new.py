"""
Главный файл запуска новой версии бота
"""
import os
import sys
import time

# Добавляем текущую директорию в путь
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Загружаем переменные окружения
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Импортируем конфигурацию и утилиты новой версии
from bot.config import settings
from bot.utils.logger import setup_logger, logger
from bot.database import init_db_pool, close_db_pool
from bot.cache import get_cache_manager

# Настраиваем логирование с ротацией
setup_logger(
    log_file=settings.logging.log_file,
    level=settings.logging.level,
    rotation=settings.logging.rotation,
    retention=settings.logging.retention
)

logger.info("=" * 60)
logger.info("🚀 Запуск новой версии TWAS Label Bot")
logger.info("=" * 60)

# Инициализация БД
logger.info("📊 Инициализация пула соединений PostgreSQL...")
if not init_db_pool():
    logger.error("❌ Не удалось инициализировать пул соединений БД")
    sys.exit(1)

logger.info("✅ Пул соединений инициализирован")

# Инициализация кэша
cache_manager = get_cache_manager()
logger.info("✅ Менеджер кэша инициализирован")

# Инициализация бота
try:
    import telebot
    from telebot import types
    
    bot = telebot.TeleBot(settings.bot.token)
    bot.user_data = {}  # Хранилище данных пользователей
    logger.info(f"✅ Бот инициализирован: @{bot.get_me().username}")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации бота: {e}")
    sys.exit(1)

# Настройка YooKassa (если доступен)
try:
    from yookassa import Configuration, Payment
    
    Configuration.account_id = settings.payment.account_id
    Configuration.secret_key = settings.payment.secret_key
    
    logger.info(f"✅ YooKassa настроен: account_id={Configuration.account_id}")
    
    # Тестируем подключение (опционально, можно закомментировать)
    # try:
    #     test_payment = Payment.create({
    #         "amount": {"value": "1.00", "currency": "RUB"},
    #         "confirmation": {"type": "redirect", "return_url": f"https://t.me/{bot.get_me().username}"},
    #         "capture": True,
    #         "description": "Test payment",
    #         "metadata": {"test": "true"}
    #     })
    #     logger.info("✅ Тест подключения YooKassa успешен")
    #     try:
    #         Payment.cancel(test_payment.id)
    #     except:
    #         pass
    # except Exception as e:
    #     logger.warning(f"⚠️ Тест YooKassa не прошел (это нормально): {e}")
        
except ImportError:
    logger.warning("⚠️ Модуль yookassa не установлен, платежи через YooKassa недоступны")
except Exception as e:
    logger.error(f"❌ Ошибка настройки YooKassa: {e}")

# Регистрация обработчиков
logger.info("📝 Регистрация обработчиков...")

from bot.handlers.common_handlers import register_common_handlers
from bot.handlers.user_handlers import register_user_handlers

register_common_handlers(bot)
register_user_handlers(bot)

logger.info("✅ Обработчики зарегистрированы")

# Функция запуска с повторными попытками
def start_bot_with_retry():
    """Запуск бота с автоматическим переподключением"""
    retry_delay = settings.bot.retry_delay
    consecutive_errors = 0
    max_consecutive_errors = settings.bot.max_retries
    
    while True:
        try:
            logger.info("🤖 Запуск polling...")
            consecutive_errors = 0
            retry_delay = settings.bot.retry_delay
            
            bot.polling(
                none_stop=True,
                interval=settings.bot.polling_interval,
                timeout=settings.bot.polling_timeout,
                long_polling_timeout=settings.bot.long_polling_timeout,
                skip_pending=settings.bot.skip_pending
            )
        except KeyboardInterrupt:
            logger.info("🛑 Бот остановлен пользователем")
            break
        except telebot.apihelper.ApiTelegramException as api_error:
            logger.error(f"❌ Telegram API ошибка: {api_error}")
            consecutive_errors += 1
            
            if "Connection reset" in str(api_error) or "Connection aborted" in str(api_error):
                logger.warning("🔄 Обрыв соединения, повтор через 2 секунды...")
                time.sleep(2)
            elif "Too Many Requests" in str(api_error):
                logger.warning("⏳ Превышен лимит запросов, ожидание 30 секунд...")
                time.sleep(30)
            elif "409" in str(api_error) or "Conflict" in str(api_error):
                logger.error("🚨 КРИТИЧНО: Обнаружено несколько экземпляров бота!")
                logger.error("🛑 Остановите все другие экземпляры бота")
                time.sleep(10)
            else:
                time.sleep(retry_delay)
                
        except ConnectionError as conn_error:
            logger.error(f"❌ Ошибка соединения: {conn_error}")
            consecutive_errors += 1
            time.sleep(retry_delay)
            
        except Exception as e:
            logger.error(f"❌ Неожиданная ошибка: {e}")
            consecutive_errors += 1
            time.sleep(retry_delay)
        
        if consecutive_errors >= max_consecutive_errors:
            logger.warning(f"⚠️ Слишком много ошибок подряд ({consecutive_errors}), увеличиваем задержку...")
            retry_delay = min(retry_delay * 2, 120)  # Максимум 120 секунд
            consecutive_errors = 0
        
        logger.info(f"🔄 Повтор через {retry_delay} секунд...")
        time.sleep(retry_delay)
        
        # Проверка соединения с БД
        try:
            from bot.database import get_db_connection, return_db_connection
            conn = get_db_connection()
            if conn:
                return_db_connection(conn)
                logger.info("✅ Соединение с БД в порядке")
            else:
                logger.error("❌ Ошибка соединения с БД")
        except Exception as db_error:
            logger.error(f"❌ Ошибка проверки БД: {db_error}")


# Обработка завершения
def cleanup():
    """Очистка ресурсов при завершении"""
    logger.info("🧹 Очистка ресурсов...")
    close_db_pool()
    cache_manager.clear()
    logger.info("✅ Ресурсы освобождены")


if __name__ == "__main__":
    try:
        start_bot_with_retry()
    finally:
        cleanup()
