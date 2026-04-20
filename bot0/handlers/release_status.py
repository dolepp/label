"""Read-only release status menu handlers."""
from __future__ import annotations

import logging

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.users import list_admin_ids


logger = logging.getLogger(__name__)

RELEASE_STATUSES = [
    "принят",
    "отправлен на площадки",
    "отгружен на площадки",
    "Релиз",
    "Отозван с площадок",
]


def _is_admin(user_id: int) -> bool:
    if user_id in PERMANENT_ADMINS or user_id in ADMIN_IDS:
        return True
    try:
        return user_id in list_admin_ids()
    except Exception as exc:
        logger.error("Could not check admin status for user %s: %s", user_id, exc)
        return False


def _status_selection_markup(release_id: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for status in RELEASE_STATUSES:
        markup.add(types.InlineKeyboardButton(f"🔄 {status.capitalize()}", callback_data=f"status_update_{release_id}_{status}"))
    return markup


def _album_status_selection_markup(album_id: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for status in RELEASE_STATUSES:
        markup.add(types.InlineKeyboardButton(f"🔄 {status.capitalize()}", callback_data=f"album_status_confirm_{album_id}_{status}"))
    markup.add(types.InlineKeyboardButton("◀️ Назад к альбому", callback_data=f"album_detail_{album_id}_admin"))
    return markup


def register_release_status_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data.startswith("change_status_"))
    def handle_change_status_request(call):
        try:
            release_id = int(call.data.split("_")[2])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"Выберите новый статус для релиза ID {release_id}:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_status_selection_markup(release_id),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("album_status_update_"))
    def handle_album_status_update(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут изменять статус", show_alert=True)
            return

        try:
            album_id = int(call.data.split("_")[3])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🔄 Выберите новый статус для альбома:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_album_status_selection_markup(album_id),
        )

