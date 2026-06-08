"""Top-level informational menu handlers."""
from __future__ import annotations

import logging
from decimal import Decimal

from telebot import types

from core.config import ADMIN_IDS, CHANNEL_USERNAME, OWNER_USERNAME, PERMANENT_ADMINS, WEB_APP_URL
from db.repositories.stats import get_user_stats, has_active_discount_promo
from db.repositories.users import list_admin_ids
from keyboards.reply import create_main_menu


logger = logging.getLogger(__name__)


def _main_markup():
    return create_main_menu()


def _is_admin(user_id: int) -> bool:
    if user_id in PERMANENT_ADMINS or user_id in ADMIN_IDS:
        return True
    try:
        return user_id in list_admin_ids()
    except Exception as exc:
        logger.error("Could not check admin status for user %s: %s", user_id, exc)
        return False


def _is_subscribed(bot, user_id: int) -> bool:
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as exc:
        logger.error("Could not check channel subscription for user %s: %s", user_id, exc)
        return False


def _require_subscription(bot, message) -> bool:
    if _is_subscribed(bot, message.from_user.id):
        return True
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"),
        types.InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription"),
    )
    bot.reply_to(message, "🔔 Для использования бота необходимо подписаться на наш канал!", reply_markup=markup)
    return False


def _money(value) -> str:
    amount = Decimal(value or 0)
    return f"{amount:,.2f}₽"


def _stats_text(stats: dict) -> str:
    return (
        "📊 Ваша статистика\n\n"
        f"🎵 Релизов: {stats['releases_count']}\n"
        f"💰 Баланс: {_money(stats['balance'])}\n"
        f"✅ Завершенных заказов: {stats['completed_orders']}\n\n"
        "📈 Продолжайте развиваться!"
    )


def _services_markup(user_id: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    buttons = [
        ("🎵 Дистрибуция", "service_distribution"),
        ("🎨 Обложка", "service_cover"),
        ("🎬 Motion обложка", "service_motion"),
        ("🎥 Видеошот", "service_videoshot"),
    ]
    if _is_admin(user_id):
        buttons.append(("📤 Выгрузка релиза за артиста", "service_release_for_artist"))
    buttons.append(("◀️ Назад", "services_back"))
    for text, callback in buttons:
        markup.add(types.InlineKeyboardButton(text, callback_data=callback))
    return markup


def _services_text() -> str:
    return (
        "🎵 Наши услуги:\n\n"
        "1. 🎵 Дистрибуция музыки - размещение вашего трека на всех площадках\n"
        "2. 🎨 Обложка - профессиональный дизайн обложки для релиза\n"
        "3. 🎬 Motion обложка - анимированная обложка для соцсетей\n"
        "4. 🎥 Видеошот - короткий вертикальный клип\n\n"
        "Выберите интересующую вас услугу:"
    )


def _send_main_menu(bot, chat_id: int) -> None:
    bot.send_message(
        chat_id,
        "🏠 Главное меню\n\nВыберите нужную опцию из меню ниже",
        reply_markup=_main_markup(),
    )


def _send_web_app_link(bot, chat_id: int, user_id: int) -> None:
    web_app_url = f"{WEB_APP_URL}?tgid={user_id}"
    markup = types.InlineKeyboardMarkup()
    if web_app_url.startswith("https://"):
        markup.add(types.InlineKeyboardButton("🌐 Открыть приложение", web_app=types.WebAppInfo(url=web_app_url)))
    else:
        markup.add(types.InlineKeyboardButton("🌐 Открыть сайт", url=web_app_url))
    bot.send_message(
        chat_id,
        "Запускаю приложение TWAS. Если окно не открылось, обновите Telegram до последней версии.",
        reply_markup=markup,
    )


def register_info_handlers(bot) -> None:
    @bot.message_handler(commands=["main"])
    def main_menu(message):
        _send_main_menu(bot, message.chat.id)

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "🎵 Наши услуги")
    def handle_services_menu(message):
        if not _require_subscription(bot, message):
            return
        bot.reply_to(message, _services_text(), reply_markup=_services_markup(message.from_user.id))
        if has_active_discount_promo(message.from_user.id):
            bot.send_message(
                message.chat.id,
                "💡 У вас есть промокод на скидку! Он будет доступен при оплате дистрибуции.",
            )

    @bot.message_handler(commands=["app", "webapp"])
    def handle_open_web_app_command(message):
        if not _require_subscription(bot, message):
            return
        _send_web_app_link(bot, message.chat.id, message.from_user.id)

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "🌐 Открыть приложение")
    def handle_open_web_app(message):
        if not _require_subscription(bot, message):
            return
        _send_web_app_link(bot, message.chat.id, message.from_user.id)

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "📊 Статистика")
    def handle_statistics(message):
        if not _require_subscription(bot, message):
            return
        stats = get_user_stats(message.from_user.id)
        if stats is None:
            bot.reply_to(message, "❌ Ошибка подключения к базе данных.")
            return
        bot.reply_to(message, _stats_text(stats))

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "ℹ️ О нас")
    def handle_about(message):
        if not _require_subscription(bot, message):
            return
        about_text = (
            "ℹ️ О TWAS Label Studio\n\n"
            "🎵 Мы работаем с 2019 года\n"
            "🌍 Дистрибуция на всех мировых площадках\n"
            "🎨 Профессиональный дизайн обложек\n"
            "🎬 Motion обложки для соцсетей\n"
            "🎤 Студия звукозаписи\n\n"
            f"📢 Наш канал: {CHANNEL_USERNAME}\n"
            f"🔗 Сайт: {WEB_APP_URL}\n\n"
            "💼 Лицензионные договоры\n"
            "📊 Детальная статистика\n"
            "💰 Прозрачные выплаты"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"))
        web_app_url = f"{WEB_APP_URL}?tgid={message.from_user.id}"
        if web_app_url.startswith("https://"):
            markup.add(types.InlineKeyboardButton("🌐 Открыть приложение", web_app=types.WebAppInfo(url=web_app_url)))
        else:
            markup.add(types.InlineKeyboardButton("🌐 Открыть сайт", url=web_app_url))
        bot.reply_to(message, about_text, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "services_back")
    def handle_services_back(call):
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        _send_main_menu(bot, call.message.chat.id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
    def handle_back_to_main(call):
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        _send_main_menu(bot, call.message.chat.id)
