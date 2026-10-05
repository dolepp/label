"""Release edit menu handlers.

Only the edit menu is modular. Actual field writes remain in legacy handlers.
"""
from __future__ import annotations

import logging

from telebot import types

from db.repositories.release_edit import get_release_edit_access
from utils.statuses import is_release_editable


logger = logging.getLogger(__name__)

UNSUPPORTED_EDIT_PREFIXES = (
    "edit_artist_name_",
    "edit_producer_",
    "edit_genre_",
    "edit_release_date_",
    "edit_performer_",
    "edit_music_author_",
)


def _edit_release_markup(release_id: int):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🎵 Название релиза", callback_data=f"edit_release_name_{release_id}"),
        types.InlineKeyboardButton("🎤 Имя артиста", callback_data=f"edit_artist_name_{release_id}"),
    )
    markup.add(
        types.InlineKeyboardButton("🎹 Продюсер", callback_data=f"edit_producer_{release_id}"),
        types.InlineKeyboardButton("🎼 Жанр", callback_data=f"edit_genre_{release_id}"),
    )
    markup.add(
        types.InlineKeyboardButton("📅 Дата релиза", callback_data=f"edit_release_date_{release_id}"),
        types.InlineKeyboardButton("👤 Исполнитель", callback_data=f"edit_performer_{release_id}"),
    )
    markup.add(types.InlineKeyboardButton("✍️ Автор музыки", callback_data=f"edit_music_author_{release_id}"))
    markup.add(types.InlineKeyboardButton("◀️ Назад к релизу", callback_data=f"my_release_detail_{release_id}"))
    return markup


def register_release_edit_handlers(bot) -> None:
    @bot.callback_query_handler(
        func=lambda call: call.data.startswith("edit_release_")
        and len(call.data.split("_")) == 3
        and call.data.split("_")[2].isdigit()
    )
    def handle_edit_release(call):
        release_id = int(call.data.split("_")[2])
        try:
            release = get_release_edit_access(release_id)
        except Exception as exc:
            logger.error("Error in handle_edit_release: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return

        if not release:
            bot.answer_callback_query(call.id, "❌ Релиз не найден", show_alert=True)
            return
        if release["user_id"] != call.from_user.id:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для редактирования этого релиза", show_alert=True)
            return
        if not is_release_editable(release["status"]):
            bot.answer_callback_query(call.id, "❌ Этот релиз нельзя редактировать", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "✏️ Выберите, что хотите изменить:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_edit_release_markup(release_id),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith(UNSUPPORTED_EDIT_PREFIXES))
    def handle_unsupported_release_edit(call):
        bot.answer_callback_query(
            call.id,
            "Пока доступно редактирование только названия релиза.",
            show_alert=True,
        )

