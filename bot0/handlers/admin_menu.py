"""Admin panel entry and navigation handlers."""
from __future__ import annotations

import logging

from telebot import types

from db.repositories.admins import ensure_admin_access


logger = logging.getLogger(__name__)


def _admin_panel_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("💿 Релизы", callback_data="admin_releases"),
        types.InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
        types.InlineKeyboardButton("📝 Отзывы", callback_data="admin_reviews"),
        types.InlineKeyboardButton("💰 Финансы", callback_data="admin_finance"),
        types.InlineKeyboardButton("🆘 Поддержка", callback_data="admin_support"),
        types.InlineKeyboardButton("🛒 Заказы", callback_data="admin_orders"),
    )
    return markup


def _check_admin(bot, user_id: int, username: str | None, alert_callback=None) -> bool:
    try:
        result = ensure_admin_access(user_id, username)
    except Exception as exc:
        logger.error("Could not check admin access for user %s: %s", user_id, exc)
        if alert_callback:
            bot.answer_callback_query(alert_callback, "❌ Ошибка проверки прав доступа", show_alert=True)
        return False

    if result.get("reason") == "db_unavailable":
        if alert_callback:
            bot.answer_callback_query(alert_callback, "❌ Ошибка подключения к базе данных", show_alert=True)
        return False
    return bool(result.get("allowed"))


def register_admin_menu_handlers(bot) -> None:
    @bot.message_handler(commands=["admin"])
    def admin_panel(message):
        allowed = _check_admin(bot, message.from_user.id, message.from_user.username)
        if not allowed:
            bot.reply_to(message, "❌ У вас недостаточно прав администратора.")
            return
        bot.reply_to(message, "🔐 Панель администратора:", reply_markup=_admin_panel_markup())

    @bot.callback_query_handler(func=lambda call: call.data == "admin_back")
    def handle_admin_back(call):
        allowed = _check_admin(bot, call.from_user.id, call.from_user.username, alert_callback=call.id)
        if not allowed:
            bot.answer_callback_query(call.id, "❌ У вас нет доступа к этой функции", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        try:
            bot.edit_message_text(
                "🔐 Панель администратора:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=_admin_panel_markup(),
            )
        except Exception as exc:
            logger.error("Could not display admin panel: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
