"""Distribution preview attachment callbacks."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _user_data(bot, user_id: int) -> dict:
    return getattr(bot, "user_data", {}).get(user_id, {})


def register_release_preview_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "preview_cover")
    def handle_preview_cover(call):
        user_data = _user_data(bot, call.from_user.id)
        file_id = user_data.get("cover_file_id")
        if not file_id:
            bot.answer_callback_query(call.id, "Обложка не загружена", show_alert=True)
            return
        try:
            bot.send_photo(call.message.chat.id, file_id, caption="🖼 Обложка релиза")
            bot.answer_callback_query(call.id)
        except Exception as exc:
            logger.error("Error sending preview cover: %s", exc)
            bot.answer_callback_query(call.id, "Не удалось отправить обложку", show_alert=True)

    @bot.callback_query_handler(func=lambda call: call.data == "preview_audio")
    def handle_preview_audio(call):
        user_data = _user_data(bot, call.from_user.id)
        file_id = user_data.get("audio_file_id")
        if not file_id:
            bot.answer_callback_query(call.id, "Трек не загружен", show_alert=True)
            return
        try:
            bot.send_audio(call.message.chat.id, file_id, caption="🎵 Трек")
            bot.answer_callback_query(call.id)
        except Exception as exc:
            logger.error("Error sending preview audio: %s", exc)
            bot.answer_callback_query(call.id, "Не удалось отправить трек", show_alert=True)

    @bot.callback_query_handler(func=lambda call: call.data == "preview_contract")
    def handle_preview_contract(call):
        user_data = _user_data(bot, call.from_user.id)
        file_id = user_data.get("contract_file_id")
        if not file_id:
            bot.answer_callback_query(call.id, "Договор не загружен", show_alert=True)
            return
        try:
            bot.send_document(call.message.chat.id, file_id, caption="📄 Договор")
            bot.answer_callback_query(call.id)
        except Exception as exc:
            logger.error("Error sending preview contract: %s", exc)
            bot.answer_callback_query(call.id, "Не удалось отправить договор", show_alert=True)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("preview_track_"))
    def handle_preview_track(call):
        user_data = _user_data(bot, call.from_user.id)
        tracks = user_data.get("tracks") or []
        try:
            idx = int(call.data.replace("preview_track_", "", 1).strip())
        except ValueError:
            bot.answer_callback_query(call.id, "Ошибка", show_alert=True)
            return
        if idx < 0 or idx >= len(tracks):
            bot.answer_callback_query(call.id, "Трек не найден", show_alert=True)
            return

        track = tracks[idx]
        track_name = track.get("track_name") or f"Трек {idx + 1}"
        chat_id = call.message.chat.id
        sent = False
        try:
            if track.get("audio_file_id"):
                bot.send_audio(chat_id, track["audio_file_id"], caption=f"🎵 {track_name}")
                sent = True
            if track.get("contract_file_id"):
                bot.send_document(chat_id, track["contract_file_id"], caption=f"📄 Договор: {track_name}")
                sent = True
            if track.get("lyrics_file_id"):
                bot.send_document(chat_id, track["lyrics_file_id"], caption=f"📝 Текст: {track_name}")
                sent = True
            if not sent:
                bot.answer_callback_query(call.id, "Нет вложений для этого трека", show_alert=True)
                return
            bot.answer_callback_query(call.id)
        except Exception as exc:
            logger.error("Error sending track attachments: %s", exc)
            bot.answer_callback_query(call.id, "Не удалось отправить вложения", show_alert=True)
