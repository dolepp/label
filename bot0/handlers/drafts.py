"""Draft list handlers for the modular bot."""
from __future__ import annotations

import json
import logging
from typing import Any

from telebot import types

from db.repositories.drafts import count_user_drafts, delete_user_draft, format_draft_datetime, list_user_drafts


logger = logging.getLogger(__name__)


def _draft_label(draft: dict[str, Any]) -> str:
    date = format_draft_datetime(draft.get("updated_at") or draft.get("created_at"))
    data_json = draft.get("data")
    if data_json:
        try:
            data = json.loads(data_json) if isinstance(data_json, str) else data_json
            artist = (data.get("artist_name") or data.get("album_artist") or "").strip()
            name = (data.get("release_name") or data.get("album_name") or "").strip()
            if artist and name:
                return f"📝 {artist} - {name} ({date})"
            if name:
                return f"📝 {name} ({date})"
            if artist:
                return f"📝 {artist} ({date})"
        except Exception:
            pass

    draft_type = draft.get("draft_type")
    type_label = "Дистрибуция" if draft_type == "distribution_legacy" else (draft_type or "Черновик")
    return f"📝 {type_label} ({date})"


def _drafts_markup(drafts: list[dict[str, Any]], total: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for draft in drafts:
        markup.add(types.InlineKeyboardButton(_draft_label(draft), callback_data=f"draft_load_{draft['id']}"))
        markup.add(types.InlineKeyboardButton(f"🗑 Удалить черновик #{draft['id']}", callback_data=f"draft_delete_prompt_{draft['id']}"))
    if total > len(drafts):
        markup.add(types.InlineKeyboardButton(f"Показаны последние {len(drafts)} из {total}", callback_data="drafts_noop"))
    markup.add(types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile"))
    return markup


def _empty_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile"))
    return markup


def _send_drafts(bot, chat_id: int, user_id: int, edit_message_id: int | None = None) -> None:
    try:
        drafts = list_user_drafts(user_id)
        total = count_user_drafts(user_id)
    except Exception as exc:
        logger.error("Could not load drafts for user %s: %s", user_id, exc)
        text = "❌ Ошибка при загрузке черновиков."
        markup = _empty_markup()
    else:
        if drafts is None or total is None:
            text = "❌ Ошибка подключения к базе данных."
            markup = _empty_markup()
        elif not drafts:
            text = "📋 Черновики\n\nУ вас пока нет сохранённых черновиков."
            markup = _empty_markup()
        else:
            text = f"📋 Ваши черновики ({total})\n\nВыберите черновик, чтобы продолжить заполнение."
            markup = _drafts_markup(drafts, total)

    if edit_message_id is None:
        bot.send_message(chat_id, text, reply_markup=markup)
    else:
        bot.edit_message_text(text, chat_id, edit_message_id, reply_markup=markup)


def register_draft_handlers(bot) -> None:
    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "📋 Черновики")
    def handle_profile_drafts(message):
        _send_drafts(bot, message.chat.id, message.from_user.id)

    @bot.callback_query_handler(func=lambda call: call.data == "profile_drafts")
    def handle_profile_drafts_callback(call):
        bot.answer_callback_query(call.id)
        _send_drafts(bot, call.message.chat.id, call.from_user.id, edit_message_id=call.message.message_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("draft_delete_prompt_"))
    def handle_draft_delete_prompt(call):
        try:
            draft_id = int(call.data.rsplit("_", 1)[1])
        except ValueError:
            bot.answer_callback_query(call.id, "❌ Неверный ID черновика", show_alert=True)
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🗑 Удалить окончательно", callback_data=f"draft_delete_confirm_{draft_id}"))
        markup.add(types.InlineKeyboardButton("◀️ Назад к черновикам", callback_data="profile_drafts"))
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"Удалить черновик #{draft_id}?\n\nЭто действие нельзя отменить.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("draft_delete_confirm_"))
    def handle_draft_delete_confirm(call):
        try:
            draft_id = int(call.data.rsplit("_", 1)[1])
        except ValueError:
            bot.answer_callback_query(call.id, "❌ Неверный ID черновика", show_alert=True)
            return

        try:
            deleted = delete_user_draft(draft_id, call.from_user.id)
        except Exception as exc:
            logger.error("Could not delete draft %s for user %s: %s", draft_id, call.from_user.id, exc)
            bot.answer_callback_query(call.id, "❌ Ошибка удаления черновика", show_alert=True)
            return

        if deleted is None:
            bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
            return
        if not deleted:
            bot.answer_callback_query(call.id, "❌ Черновик не найден", show_alert=True)
            return

        bot.answer_callback_query(call.id, "✅ Черновик удалён")
        _send_drafts(bot, call.message.chat.id, call.from_user.id, edit_message_id=call.message.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "drafts_noop")
    def handle_drafts_noop(call):
        bot.answer_callback_query(call.id)
