"""Registration, /start and subscription-gated onboarding handlers."""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Callable

from telebot import types

from keyboards.reply import create_main_menu
from db.repositories.users import update_user_channel_by_username


logger = logging.getLogger(__name__)

bot = None
get_pg_connection: Callable[..., Any] | None = None
return_pg_connection: Callable[..., Any] | None = None
handle_referral_registration: Callable[..., Any] | None = None
notify_referrer_about_visit: Callable[..., Any] | None = None
CHANNEL_USERNAME = "@twaslabel"
SUBSCRIPTION_CHAT_ID = -1002021934191
_subscription_cache: dict[int, tuple[bool, float]] = {}
_SUBSCRIPTION_CACHE_TTL = 300


def configure_onboarding(**context: Any) -> None:
    """Inject runtime dependencies without importing label.py."""
    globals().update({key: value for key, value in context.items() if value is not None})


def _require(name: str) -> Any:
    value = globals().get(name)
    if value is None:
        raise RuntimeError(f"onboarding dependency is not configured: {name}")
    return value


def check_channel_subscription(user_id: int, force_check: bool = False) -> bool:
    """Check required channel subscription with a short in-memory cache."""
    active_bot = _require("bot")
    now = time.time()
    if not force_check and user_id in _subscription_cache:
        is_subscribed, cached_at = _subscription_cache[user_id]
        if now - cached_at < _SUBSCRIPTION_CACHE_TTL:
            return is_subscribed
    try:
        chat_member = active_bot.get_chat_member(CHANNEL_USERNAME, user_id)
        is_subscribed = chat_member.status in ["member", "administrator", "creator"]
        _subscription_cache[user_id] = (is_subscribed, now)
        return is_subscribed
    except Exception as exc:
        logger.error("Error checking channel subscription for user %s: %s", user_id, exc)
        if "chat not found" in str(exc).lower() or "bot is not a member" in str(exc).lower():
            logger.error("Bot is not added to the channel as administrator")
        return False


def check_subscription(user_id: int) -> bool:
    """Compatibility check used by the subscription callback."""
    return check_channel_subscription(user_id, force_check=True)


def require_channel_subscription(func):
    """Decorator for handlers that require subscription to the label channel."""
    def wrapper(message):
        user_id = message.from_user.id
        active_bot = _require("bot")
        if not check_channel_subscription(user_id):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
            markup.add(types.InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription"))
            active_bot.reply_to(
                message,
                "🔔 Для использования бота необходимо подписаться на наш канал!\n\n"
                f"📢 Канал: {CHANNEL_USERNAME}\n"
                "🎵 Здесь мы публикуем новости, релизы и важные обновления\n\n"
                "После подписки нажмите кнопку 'Я подписался'",
                reply_markup=markup,
            )
            return None
        return func(message)

    return wrapper


def _normalize_channel(raw: str) -> str:
    channel = (raw or "").strip()
    if not (channel.startswith("@") or channel.startswith("https://t.me/") or channel.startswith("t.me/")):
        raise ValueError("Неверный формат ссылки. Пожалуйста, используйте формат @channel или https://t.me/channel")
    if channel.startswith("https://t.me/"):
        return channel.split("/")[-1]
    if channel.startswith("t.me/"):
        return channel.split("/")[-1]
    return channel[1:]


def _start_impl(message):
    active_bot = _require("bot")
    conn_factory = _require("get_pg_connection")
    return_conn = _require("return_pg_connection")
    user_id = message.from_user.id
    username = message.from_user.username

    referral_code = None
    if message.text and len(message.text.split()) > 1:
        referral_code = message.text.split()[1].strip()

    conn = None
    cursor = None
    try:
        conn = conn_factory()
        if not conn:
            active_bot.reply_to(message, "Извините, произошла ошибка при подключении к базе данных.")
            return

        cursor = conn.cursor()
        cursor.execute("SELECT id, tg FROM label WHERE telegram_id = %s", (user_id,))
        row = cursor.fetchone()
        if not row:
            # Serialize new registrations and MAX(id) allocation until commit.
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", (72419001,))
            cursor.execute("SELECT id, tg FROM label WHERE telegram_id = %s", (user_id,))
            row = cursor.fetchone()

        is_new_user = False
        if row:
            current_tg = row[1]
            if username and current_tg != username:
                cursor.execute("UPDATE label SET tg = %s WHERE telegram_id = %s", (username, user_id))
            registration_text = "С возвращением!"
        else:
            is_new_user = True
            cursor.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM label")
            result = cursor.fetchone()
            new_id = result[0] if result else 1
            cursor.execute(
                "INSERT INTO label (id, tg, telegram_id, admin, artist, created_date) VALUES (%s, %s, %s, %s, %s, %s)",
                (new_id, username, user_id, 0, 0, datetime.now()),
            )
            registration_text = "Добро пожаловать! Вы успешно зарегистрированы в системе."
            logger.info("New user registered: %s (username: %s) with ID %s", user_id, username or "не указан", new_id)

        if referral_code and is_new_user and handle_referral_registration:
            handle_referral_registration(cursor, user_id, referral_code, conn)
        conn.commit()
        active_bot.reply_to(message, registration_text)
        if referral_code and not is_new_user and notify_referrer_about_visit:
            notify_referrer_about_visit(referral_code, user_id, username)
    except Exception as exc:
        if conn:
            conn.rollback()
        logger.error("Database error in start handler: %s", exc)
        active_bot.reply_to(message, "Произошла ошибка при обработке вашего запроса.")
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_conn(conn)

    welcome_text = (
        "Добро пожаловать в talk with a star // label  ⭐️\n\n"
        "Мы - музыкальный лейбл и мы поможем вам:\n"
        "• Выпустить трек на все площадки 🎧\n"
        "• Создать обложку для релиза 🎨\n"
        "• Заказать историю к релизу\n"
        "• Получить продвижение 📈\n\n"
        "Используйте меню ниже для навигации 👇\n\n"
        "💡 Команды:\n"
        "/start - Главная страница\n"
        "/main - Вернуться в главное меню\n"
        "/cancel - Отменить текущую операцию"
    )
    active_bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_menu())


def register_onboarding_handlers(bot, context: dict | None = None) -> None:
    configure_onboarding(bot=bot, **(context or {}))

    @bot.message_handler(commands=["start"])
    @require_channel_subscription
    def start(message):
        _start_impl(message)

    @bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
    def callback_check_subscription(call):
        if check_subscription(call.from_user.id):
            bot.delete_message(call.message.chat.id, call.message.message_id)
            start_message = type("StartMessage", (), {
                "text": "/start",
                "from_user": call.from_user,
                "chat": call.message.chat,
                "message_id": getattr(call.message, "message_id", None),
            })()
            _start_impl(start_message)
        else:
            bot.answer_callback_query(
                call.id,
                "Окак вы все еще не подписаны на канал. Подпишитесь для использования бота.",
                show_alert=True,
            )

    def save_channel(message):
        try:
            channel = _normalize_channel(message.text or "")
        except ValueError as exc:
            bot.reply_to(message, f"❌ {exc}")
            bot.register_next_step_handler(message, save_channel)
            return

        try:
            update_user_channel_by_username(message.from_user.username, channel)
            logger.info("User %s added channel %s", message.from_user.username, channel)
            bot.reply_to(
                message,
                f"✅ Канал {channel} успешно сохранен!\n\n"
                "Регистрация завершена. Теперь вы можете пользоваться всеми функциями бота.",
                reply_markup=create_main_menu(),
            )
        except Exception as exc:
            logger.error("Error saving channel: %s", exc)
            bot.reply_to(message, "❌ Произошла ошибка при сохранении канала. Попробуйте позже.")

    @bot.callback_query_handler(func=lambda call: call.data == "skip_channel")
    def skip_channel_handler(call):
        try:
            update_user_channel_by_username(call.from_user.username, "не указал")
            logger.info("User %s skipped channel input", call.from_user.username)
            bot.edit_message_text(
                "✅ Регистрация успешно завершена!\n\n"
                "Теперь вы можете пользоваться всеми функциями бота.\n\n"
                "Выберите действие в меню ниже 👇",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=create_main_menu(),
            )
        except Exception as exc:
            logger.error("Error handling skip_channel: %s", exc)
            bot.answer_callback_query(call.id, "❌ Произошла ошибка. Попробуйте позже.")

    @bot.callback_query_handler(func=lambda call: call.data == "add_channel")
    def request_channel_handler(call):
        bot.edit_message_text(
            "Пожалуйста, отправьте ссылку на ваш Telegram-канал в формате @channel или https://t.me/channel",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.register_next_step_handler(call.message, save_channel)
