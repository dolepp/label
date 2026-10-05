"""Admin release management entry handlers."""
from __future__ import annotations

import html
import logging

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.admin_users import list_admin_user_cards
from db.repositories.admin_user_releases import (
    get_artist_release_stats,
    list_artist_names,
    list_artist_releases,
    list_recent_releases,
)
from db.repositories.users import list_admin_ids
from utils.statuses import release_status_label


logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    if user_id in PERMANENT_ADMINS or user_id in ADMIN_IDS:
        return True
    try:
        return user_id in list_admin_ids()
    except Exception as exc:
        logger.error("Could not check admin status for user %s: %s", user_id, exc)
        return False


def _display_name(user: dict) -> str:
    if user.get("name") and user.get("tg"):
        return f"{user['name']} (@{user['tg']})"
    return f"ID: {user['telegram_id']}"


def _admin_releases_text(users: list[dict]) -> str:
    if not users:
        return "🤷‍♀️ В базе данных нет зарегистрированных пользователей."
    return "💿 Управление релизами\n\nВыберите пользователя для просмотра его релизов:"


def _admin_releases_markup(users: list[dict]):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for user in users:
        markup.add(
            types.InlineKeyboardButton(
                _display_name(user),
                callback_data=f"user_releases_{user['telegram_id']}",
            )
        )
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))
    return markup


def _date_text(value) -> str:
    return value.strftime("%d.%m.%Y") if value else "нет даты"


def _recent_releases_text(releases: list[dict]) -> str:
    if not releases:
        return "❌ В базе нет релизов"
    lines = ["📀 Последние 10 релизов:", ""]
    for release in releases:
        artist = html.escape(str(release.get("artist_name") or "Не указан"))
        username = html.escape(str(release.get("username") or "нет username"))
        name = html.escape(str(release.get("release_name") or "Без названия"))
        status = html.escape(str(release.get("status") or "статус не указан"))
        lines.extend([
            f"🎤 <b>{artist}</b> (@{username})",
            f"🎵 {name}",
            f"📅 {_date_text(release.get('release_date'))}",
            f"🟢 {status}",
            "",
        ])
    return "\n".join(lines)


def _artist_info_text(artist_name: str, stats: dict) -> str:
    first = stats.get("first_release")
    last = stats.get("last_release")
    return (
        f"🎤 Исполнитель: {artist_name}\n\n"
        f"📀 Всего релизов: {stats.get('release_count', 0)}\n"
        f"📅 Первый релиз: {_date_text(first) if first else 'нет данных'}\n"
        f"📅 Последний релиз: {_date_text(last) if last else 'нет данных'}"
    )


def _artist_releases_text(artist_name: str, releases: list[dict]) -> str:
    if not releases:
        return f"❌ У исполнителя {artist_name} нет релизов"
    lines = [f"📀 Релизы исполнителя {artist_name}:", ""]
    for release in releases:
        lines.extend([
            f"🎵 {release.get('release_name') or 'Без названия'}",
            f"📅 {_date_text(release.get('release_date'))}",
            f"🟢 {release_status_label(release.get('status'))}",
            "",
        ])
    return "\n".join(lines)


def register_admin_release_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "admin_releases")
    def handle_admin_releases(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
            return

        try:
            users = list_admin_user_cards()
        except Exception as exc:
            logger.error("PostgreSQL error in handle_admin_releases: %s", exc)
            bot.answer_callback_query(call.id, "❌ Произошла ошибка при получении списка пользователей.", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _admin_releases_text(users),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_admin_releases_markup(users),
        )



    @bot.callback_query_handler(func=lambda call: call.data == "releases_all")
    def show_all_releases(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
            return
        try:
            releases = list_recent_releases(limit=10)
        except Exception as exc:
            logger.error("Error in show_all_releases: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_releases"))
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _recent_releases_text(releases),
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=markup,
        )

    @bot.callback_query_handler(func=lambda call: call.data == "releases_artists")
    def show_artists_list(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
            return
        try:
            artists = list_artist_names()
        except Exception as exc:
            logger.error("Error in show_artists_list: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return
        if not artists:
            bot.edit_message_text("❌ Нет исполнителей в базе данных", call.message.chat.id, call.message.message_id)
            return
        markup = types.InlineKeyboardMarkup(row_width=2)
        for artist in artists:
            markup.add(types.InlineKeyboardButton(str(artist), callback_data=f"artist_{artist}"))
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_releases"))
        bot.answer_callback_query(call.id)
        bot.edit_message_text("👥 Список исполнителей:", call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("artist_") and not call.data.startswith("artist_releases_"))
    def show_artist_info(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
            return
        artist_name = call.data.split("_", 1)[1]
        try:
            stats = get_artist_release_stats(artist_name)
        except Exception as exc:
            logger.error("Error in show_artist_info: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("📀 Релизы исполнителя", callback_data=f"artist_releases_{artist_name}"),
            types.InlineKeyboardButton("◀️ Назад к списку", callback_data="releases_artists"),
        )
        bot.answer_callback_query(call.id)
        bot.edit_message_text(_artist_info_text(artist_name, stats), call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("artist_releases_"))
    def show_artist_releases(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
            return
        artist_name = call.data.split("_", 2)[2]
        try:
            releases = list_artist_releases(artist_name, limit=10)
        except Exception as exc:
            logger.error("Error in show_artist_releases: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("◀️ Назад к исполнителю", callback_data=f"artist_{artist_name}"),
            types.InlineKeyboardButton("◀️ Назад к списку", callback_data="releases_artists"),
        )
        bot.answer_callback_query(call.id)
        bot.edit_message_text(_artist_releases_text(artist_name, releases), call.message.chat.id, call.message.message_id, reply_markup=markup)
