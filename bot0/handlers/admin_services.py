"""Admin service settings menu handlers."""
from __future__ import annotations

import logging

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.users import list_admin_ids


logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    if user_id in PERMANENT_ADMINS or user_id in ADMIN_IDS:
        return True
    try:
        return user_id in list_admin_ids()
    except Exception as exc:
        logger.error("Could not check admin status for user %s: %s", user_id, exc)
        return False


def _admin_services_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📤 Загрузить договор на бит", callback_data="admin_upload_contract"),
        types.InlineKeyboardButton("📝 Управление шаблонами", callback_data="admin_templates"),
        types.InlineKeyboardButton("⚙️ Настройки сервисов", callback_data="admin_service_settings"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"),
    )
    return markup


def _templates_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✉️ Шаблон письма", callback_data="template_email"),
        types.InlineKeyboardButton("📝 Шаблон договора", callback_data="template_contract"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_services"),
    )
    return markup


def _service_settings_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("💰 Цены на услуги", callback_data="service_prices"),
        types.InlineKeyboardButton("⏳ Время обработки", callback_data="service_times"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_services"),
    )
    return markup


def _require_admin(bot, call) -> bool:
    if _is_admin(call.from_user.id):
        return True
    bot.answer_callback_query(call.id, "У вас нет доступа к этой функции", show_alert=True)
    return False


def register_admin_service_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "admin_services")
    def handle_admin_services(call):
        if not _require_admin(bot, call):
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "⚙️ Управление сервисами и настройками:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_admin_services_markup(),
        )

    @bot.callback_query_handler(func=lambda call: call.data == "admin_templates")
    def handle_templates_management(call):
        if not _require_admin(bot, call):
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "📝 Управление шаблонами:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_templates_markup(),
        )

    @bot.callback_query_handler(func=lambda call: call.data == "admin_service_settings")
    def handle_service_settings(call):
        if not _require_admin(bot, call):
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "⚙️ Настройки сервисов:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_service_settings_markup(),
        )
