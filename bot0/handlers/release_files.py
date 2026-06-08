"""Release attachment and single file sending handlers."""
from __future__ import annotations

import logging

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.release_files import get_release_attachments, get_release_file_id
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


def _send_media_safely(bot, chat_id: int, file_id: str, kind: str, caption: str | None = None) -> bool:
    if not file_id:
        return False
    kinds_order = ["document"]
    if kind == "photo":
        kinds_order = ["photo", "document"]
    elif kind == "audio":
        kinds_order = ["audio", "document"]

    for media_kind in kinds_order:
        try:
            if media_kind == "photo":
                bot.send_photo(chat_id, file_id, caption=caption)
            elif media_kind == "audio":
                bot.send_audio(chat_id, file_id, caption=caption)
            else:
                bot.send_document(chat_id, file_id, caption=caption)
            return True
        except Exception as exc:
            logger.info("send media %s failed for %s: %s", media_kind, file_id, exc)

    if isinstance(file_id, str) and file_id.lower().startswith(("http://", "https://")):
        try:
            prefix = f"{caption}\n" if caption else ""
            bot.send_message(chat_id, f"{prefix}{file_id}")
            return True
        except Exception as exc:
            logger.warning("URL fallback failed for %s: %s", file_id, exc)
    return False


def _send_single_file(bot, chat_id: int, file_id: str, file_type: str) -> bool:
    if file_type == "contract":
        return _send_media_safely(bot, chat_id, file_id, "document", "📝 Контракт на релиз")
    if file_type == "cover":
        return _send_media_safely(bot, chat_id, file_id, "photo", "🎨 Обложка релиза")
    if file_type == "audio":
        return _send_media_safely(bot, chat_id, file_id, "audio", "🎧 Аудиофайл релиза")
    return False


def register_release_file_handlers(bot) -> None:

    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_view_release_"))
    def handle_admin_view_release(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Недостаточно прав", show_alert=True)
            return
        try:
            release_id = int(call.data.split("_")[-1])
            attachments = get_release_attachments(release_id)
            if not attachments:
                bot.answer_callback_query(call.id, "❌ Release not found", show_alert=True)
                return
            sent = 0
            chat_id = call.message.chat.id
            if attachments.get("cover_file_id") and _send_media_safely(bot, chat_id, attachments["cover_file_id"], "photo", "🎨 Release Cover"):
                sent += 1
            if attachments.get("audio_file_id") and _send_media_safely(bot, chat_id, attachments["audio_file_id"], "audio", "🎧 Audio Track"):
                sent += 1
            if attachments.get("contract_file_id") and _send_media_safely(bot, chat_id, attachments["contract_file_id"], "document", "📝 Beat Contract"):
                sent += 1
            if attachments.get("lyrics_file_id") and _send_media_safely(bot, chat_id, attachments["lyrics_file_id"], "document", "📜 Song Lyrics"):
                sent += 1
            bot.answer_callback_query(call.id, "✅ Attachments sent" if sent else "❌ Нет вложений", show_alert=sent == 0)
        except Exception as exc:
            logger.error("Error in handle_admin_view_release: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Error: {exc}", show_alert=True)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("show_attachments_"))
    def handle_show_attachments(call):
        try:
            parts = call.data.split("_")
            release_id = int(parts[2])
            admin_mode = len(parts) > 3 and parts[3] == "admin"
            if admin_mode and not _is_admin(call.from_user.id):
                bot.answer_callback_query(call.id, "❌ Недостаточно прав", show_alert=True)
                return
            attachments = get_release_attachments(release_id, None if admin_mode else call.from_user.id)
            if not attachments:
                bot.answer_callback_query(call.id, "❌ Релиз не найден", show_alert=True)
                return

            sent_count = 0
            chat_id = call.message.chat.id
            if attachments.get("is_track") and attachments.get("album_id"):
                if attachments.get("album_cover_file_id"):
                    if not _send_media_safely(bot, chat_id, attachments["album_cover_file_id"], "photo", "🎨 Обложка альбома"):
                        bot.send_message(chat_id, f"🎨 Обложка альбома: {attachments['album_cover_file_id']}")
                    sent_count += 1
                if attachments.get("audio_file_id") and _send_media_safely(bot, chat_id, attachments["audio_file_id"], "audio", "🎧 Аудио трека"):
                    sent_count += 1
                if attachments.get("lyrics_file_id") and _send_media_safely(bot, chat_id, attachments["lyrics_file_id"], "document", "📜 Текст песни"):
                    sent_count += 1
                if attachments.get("contract_file_id") and _send_media_safely(bot, chat_id, attachments["contract_file_id"], "document", "📄 Контракт на бит (для трека)"):
                    sent_count += 1
            else:
                if attachments.get("cover_file_id") and _send_media_safely(bot, chat_id, attachments["cover_file_id"], "photo", "🎨 Обложка релиза"):
                    sent_count += 1
                if attachments.get("audio_file_id") and _send_media_safely(bot, chat_id, attachments["audio_file_id"], "audio", "🎧 Аудио релиза"):
                    sent_count += 1
                if attachments.get("contract_file_id") and _send_media_safely(bot, chat_id, attachments["contract_file_id"], "document", "📄 Контракт на бит"):
                    sent_count += 1
                if attachments.get("lyrics_file_id") and _send_media_safely(bot, chat_id, attachments["lyrics_file_id"], "document", "📜 Текст песни"):
                    sent_count += 1

            videoshot_url = attachments.get("videoshot_url")
            if videoshot_url and str(videoshot_url).lower() != "нет":
                bot.send_message(chat_id, f"🎥 Ссылка на видеошот: {videoshot_url}")
                sent_count += 1

            if sent_count == 0:
                bot.answer_callback_query(call.id, "❌ В этом релизе нет доступных вложений", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "✅ Все вложения отправлены")
        except Exception as exc:
            logger.error("Error showing attachments: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith(("view_cover_", "view_audio_")) or call.data.startswith("view_release_contract_")
    )
    def handle_view_file(call):
        try:
            if call.data.startswith("view_release_contract_"):
                release_id = int(call.data.split("_")[3])
                file_type = "contract"
            elif call.data.startswith("view_cover_"):
                release_id = int(call.data.split("_")[2])
                file_type = "cover"
            else:
                release_id = int(call.data.split("_")[2])
                file_type = "audio"

            file_id = get_release_file_id(release_id, file_type)
            if not file_id:
                bot.answer_callback_query(call.id, "❌ Файл не найден", show_alert=True)
                return
            if not _send_single_file(bot, call.message.chat.id, file_id, file_type):
                bot.answer_callback_query(call.id, "❌ Не удалось отправить файл", show_alert=True)
                return
            bot.answer_callback_query(call.id, "Файл отправлен в чат")
        except Exception as exc:
            logger.error("Error in handle_view_file: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
