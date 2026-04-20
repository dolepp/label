"""Admin per-user release list handlers."""
from __future__ import annotations

import logging

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.admin_user_releases import list_admin_user_releases
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


def _release_date(value) -> str:
    return value.strftime("%d.%m.%Y") if value else "дата не указана"


def _admin_user_releases_text(releases: dict) -> str:
    total = len(releases.get("albums", [])) + len(releases.get("singles", []))
    if total == 0:
        return "📀 Релизы пользователя:\n\n❌ У пользователя нет релизов"
    return "📀 Релизы пользователя:"


def _admin_user_releases_markup(user_id: int, releases: dict):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for album in releases.get("albums", []):
        markup.add(
            types.InlineKeyboardButton(
                f"💿 {album.get('release_name')} ({_release_date(album.get('release_date'))}) - {album.get('status')}",
                callback_data=f"album_detail_{album['id']}_admin",
            )
        )
    for single in releases.get("singles", []):
        markup.add(
            types.InlineKeyboardButton(
                f"🎵 {single.get('release_name')} ({_release_date(single.get('release_date'))}) - {single.get('status')}",
                callback_data=f"my_release_detail_{single['id']}_admin",
            )
        )
    markup.add(types.InlineKeyboardButton("◀️ Назад к списку пользователей", callback_data="admin_releases"))
    markup.add(types.InlineKeyboardButton("◀️ К пользователям", callback_data="admin_users"))
    return markup


def register_admin_user_release_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data.startswith("user_releases_"))
    def handle_user_releases(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
            return

        try:
            user_id = int(call.data.split("_")[2])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return

        try:
            releases = list_admin_user_releases(user_id)
        except Exception as exc:
            logger.error("Error in admin user releases: %s", exc)
            bot.answer_callback_query(call.id, "❌ Произошла ошибка при получении списка релизов.", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _admin_user_releases_text(releases),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_admin_user_releases_markup(user_id, releases),
        )

