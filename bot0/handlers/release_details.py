"""Read-only release and album detail handlers."""
from __future__ import annotations

import logging

from telebot import types

from db.repositories.release_details import get_album_detail, get_release_detail


logger = logging.getLogger(__name__)


def _date_text(value) -> str:
    return value.strftime("%d.%m.%Y") if value else "дата не указана"


def _yes_no(value) -> str:
    return "Да" if value else "Нет"


def _album_detail_text(album: dict) -> str:
    return (
        f"💿 Альбом: {album.get('release_name')}\n\n"
        f"📅 Дата релиза: {_date_text(album.get('release_date'))}\n"
        f"🟢 Статус: {album.get('status')}\n"
        f"🔖 UPC код: {album.get('upc_code') or 'не указан'}\n\n"
        "🎵 Треки в альбоме:"
    )


def _release_detail_text(release: dict) -> str:
    preview = f"{release.get('preview_start')} сек" if release.get("preview_start") else "Не указано"
    return (
        f"📀 Детали релиза: {release.get('release_name')}\n\n"
        f"🎵 Тип: {release.get('release_type')}\n"
        f"🎤 Артист: {release.get('artist_name')}\n"
        f"🎹 Продюсер: {release.get('producer') or 'Не указан'}\n"
        f"🎼 Жанр: {release.get('genre')}\n"
        f"📅 Дата релиза: {_date_text(release.get('release_date'))}\n"
        f"👤 Исполнитель: {release.get('performer_name')}\n"
        f"✍️ Автор музыки: {release.get('music_author')}\n"
        f"🔞 Explicit: {_yes_no(release.get('explicit_content'))}\n"
        f"🟢 Яндекс 'Скоро': {_yes_no(release.get('yandex_soon'))}\n"
        f"🔗 Создать ссылки: {_yes_no(release.get('create_links'))}\n"
        f"📱 TikTok коммерч.: {_yes_no(release.get('tiktok_commercial'))}\n"
        f"🎵 TikTok полная версия: {_yes_no(release.get('tiktok_full_version'))}\n"
        f"⏱️ Секунды TikTok: {preview}\n"
        f"🟢 Статус: {release.get('status')}\n"
        f"🔖 UPC код: {release.get('upc_code') or 'пока что нет'}\n"
    )


def _album_detail_markup(album: dict, admin_mode: bool):
    album_id = album["id"]
    markup = types.InlineKeyboardMarkup(row_width=1)
    if admin_mode:
        markup.add(types.InlineKeyboardButton("🔄 Изменить статус альбома", callback_data=f"album_status_update_{album_id}"))
        markup.add(types.InlineKeyboardButton("🏷️ Изменить UPC код альбома", callback_data=f"album_upc_update_{album_id}"))
        markup.add(types.InlineKeyboardButton("🔗 Изменить ссылку", callback_data=f"quick_link_menu_{album_id}"))
        markup.add(types.InlineKeyboardButton("", callback_data="separator"))

    for track in album.get("tracks", []):
        callback = f"my_release_detail_{track['id']}_admin" if admin_mode else f"my_release_detail_{track['id']}"
        markup.add(types.InlineKeyboardButton(f"{track.get('track_number')}. {track.get('release_name')}", callback_data=callback))

    if admin_mode:
        markup.add(types.InlineKeyboardButton("◀️ Назад к релизам", callback_data=f"user_releases_{album['user_id']}"))
    else:
        markup.add(types.InlineKeyboardButton("◀️ Назад к моим релизам", callback_data="back_to_my_releases"))
    return markup


def _release_detail_markup(release: dict, admin_mode: bool):
    release_id = release["id"]
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton(
            "📎 Показать вложения",
            callback_data=f"show_attachments_{release_id}_admin" if admin_mode else f"show_attachments_{release_id}",
        )
    )

    if not admin_mode and release.get("status") in ["В обработке", "Готов к отгрузке"]:
        markup.add(types.InlineKeyboardButton("✏️ Редактировать релиз", callback_data=f"edit_release_{release_id}"))

    if admin_mode:
        markup.add(
            types.InlineKeyboardButton("🔄 Изменить статус", callback_data=f"change_status_{release_id}"),
            types.InlineKeyboardButton("🔖 Изменить UPC код", callback_data=f"change_upc_{release_id}"),
        )
        markup.add(types.InlineKeyboardButton("🔗 Изменить ссылку", callback_data=f"quick_link_menu_{release_id}"))
        markup.add(types.InlineKeyboardButton("◀️ Назад к релизам", callback_data=f"user_releases_{release['user_id']}"))
    else:
        markup.add(types.InlineKeyboardButton("◀️ Назад к моим релизам", callback_data="back_to_my_releases"))
    return markup


def register_release_detail_handlers(bot) -> None:
    @bot.callback_query_handler(
        func=lambda call: call.data.startswith(("album_detail_", "my_release_detail_")) and not call.data.endswith("_admin")
    )
    def handle_release_callback(call):
        try:
            if call.data.startswith("album_detail_"):
                album_id = int(call.data.split("_")[2])
                album = get_album_detail(album_id, user_id=call.from_user.id)
                if not album:
                    bot.answer_callback_query(call.id, "❌ Альбом не найден", show_alert=True)
                    return
                bot.answer_callback_query(call.id)
                bot.edit_message_text(
                    f"<code>{_album_detail_text(album)}</code>",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=_album_detail_markup(album, admin_mode=False),
                )
                return

            release_id = int(call.data.split("_")[3])
            release = get_release_detail(release_id, user_id=call.from_user.id)
            if not release:
                bot.answer_callback_query(call.id, "❌ Релиз не найден", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                _release_detail_text(release),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=_release_detail_markup(release, admin_mode=False),
            )
        except Exception as exc:
            logger.error("Error handling release callback: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith(("album_detail_", "my_release_detail_")) and call.data.endswith("_admin")
    )
    def handle_admin_release_details(call):
        try:
            if call.data.startswith("album_detail_"):
                album_id = int(call.data.split("_")[2])
                album = get_album_detail(album_id)
                if not album:
                    bot.answer_callback_query(call.id, "❌ Альбом не найден", show_alert=True)
                    return
                bot.answer_callback_query(call.id)
                bot.edit_message_text(
                    f"<code>{_album_detail_text(album)}</code>",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=_album_detail_markup(album, admin_mode=True),
                )
                return

            release_id = int(call.data.split("_")[3])
            release = get_release_detail(release_id)
            if not release:
                bot.answer_callback_query(call.id, "❌ Релиз не найден", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            bot.edit_message_text(
                _release_detail_text(release),
                call.message.chat.id,
                call.message.message_id,
                reply_markup=_release_detail_markup(release, admin_mode=True),
            )
        except Exception as exc:
            logger.error("Error handling admin release callback: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)

