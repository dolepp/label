"""Admin service settings menu handlers."""
from __future__ import annotations

import logging

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS, SERVICE_PRICES, SUPPORT_HOURS
from db.repositories.service_files import get_latest_beat_contract_file, save_beat_contract_file
from db.repositories.users import list_admin_ids
from utils.security import validate_file_upload


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
        types.InlineKeyboardButton("📝 Текущий договор на бит", callback_data="template_contract"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_services"),
    )
    return markup


def _service_settings_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("💰 Цены на услуги", callback_data="service_prices"),
        types.InlineKeyboardButton("⏰ Часы работы поддержки", callback_data="service_times"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_services"),
    )
    return markup



def _save_contract_file_message(bot, message) -> None:
    is_valid, error_message, file_id = validate_file_upload(
        message,
        allowed_extensions=[".pdf", ".doc", ".docx"],
        max_size_mb=10,
        required_type="document",
    )
    if not is_valid:
        bot.reply_to(message, error_message)
        return
    if not _is_admin(message.from_user.id):
        bot.reply_to(message, "❌ У вас нет прав для загрузки файла")
        return
    try:
        save_beat_contract_file(file_id, message.from_user.id)
        bot.reply_to(message, "✅ Файл договора успешно загружен и доступен пользователям")
    except Exception as exc:
        logger.error("PostgreSQL error in save beat contract file: %s", exc)
        bot.reply_to(message, "❌ Произошла ошибка при сохранении файла.")

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

    @bot.callback_query_handler(func=lambda call: call.data == "template_contract")
    def handle_template_contract(call):
        if not _require_admin(bot, call):
            return
        try:
            file_id = get_latest_beat_contract_file()
        except Exception as exc:
            logger.error("Could not load beat contract template: %s", exc)
            file_id = None
        if not file_id:
            bot.answer_callback_query(call.id, "Договор ещё не загружен. Используйте «📤 Загрузить договор на бит».", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.send_document(call.message.chat.id, file_id, caption="📝 Текущий договор для битмейкеров")

    @bot.callback_query_handler(func=lambda call: call.data == "service_prices")
    def handle_service_prices(call):
        if not _require_admin(bot, call):
            return
        bot.answer_callback_query(call.id)
        names = {"distribution": "Дистрибуция (Single)", "cover": "Обложка", "motion": "Motion-обложка", "videoshot": "Видеошот"}
        lines = ["💰 Текущие цены\n"] + [f"{names.get(key, key)}: {price}₽" for key, price in SERVICE_PRICES.items()]
        lines.append("\nMaxi Single 1799₽ · EP 2399₽ · ALBUM 2899₽")
        lines.append("\nЦены задаются в bot0/core/config.py и site/api.py.")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_service_settings"))
        bot.edit_message_text("\n".join(lines), call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "service_times")
    def handle_service_times(call):
        if not _require_admin(bot, call):
            return
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_service_settings"))
        bot.edit_message_text(
            f"⏰ Часы работы поддержки: {SUPPORT_HOURS}\n\nМеняются переменной окружения SUPPORT_HOURS в .env.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )

    @bot.callback_query_handler(func=lambda call: call.data == "admin_upload_contract")
    def request_contract_file(call):
        if not _require_admin(bot, call):
            return
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "📤 Отправьте файл договора для битмейкеров")
        bot.register_next_step_handler(call.message, lambda message: _save_contract_file_message(bot, message))
