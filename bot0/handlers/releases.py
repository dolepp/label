"""User release list handlers for the modular bot."""
from __future__ import annotations

import logging

from telebot import types

from db.repositories.releases import format_release_date, list_user_release_cards


logger = logging.getLogger(__name__)


def _release_callback(release: dict) -> str:
    prefix = "album_detail" if release["is_album"] else "my_release_detail"
    return f"{prefix}_{release['id']}"


def _release_button_text(release: dict) -> str:
    icon = "💿" if release["is_album"] else "🎵"
    name = release["release_name"] or "Без названия"
    date = format_release_date(release["release_date"])
    status = release["status"] or "статус не указан"
    return f"{icon} {name} ({date}) - {status}"


def _releases_text(releases: list[dict], all_items: bool = False) -> str:
    if not releases:
        return "💿 У вас пока нет релизов\n\nСоздайте свой первый релиз."

    title = "📀 Все ваши релизы:" if all_items else "📀 Ваши релизы:"
    lines = [title, ""]
    for index, release in enumerate(releases, 1):
        kind = "альбом" if release["is_album"] else "релиз"
        lines.append(
            f"{index}. {release['release_name'] or 'Без названия'} "
            f"({format_release_date(release['release_date'])}) - {release['status'] or 'статус не указан'} [{kind}]"
        )
    return "\n".join(lines)


def _releases_markup(releases: list[dict], all_items: bool = False):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for release in releases:
        markup.add(types.InlineKeyboardButton(_release_button_text(release), callback_data=_release_callback(release)))

    if releases and not all_items:
        markup.add(types.InlineKeyboardButton("📀 Все релизы", callback_data="all_releases"))
    if not releases:
        markup.add(types.InlineKeyboardButton("➕ Создать релиз", callback_data="service_distribution"))
    markup.add(types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile"))
    return markup


def _send_releases(bot, chat_id: int, user_id: int, edit_message_id: int | None = None, all_items: bool = False) -> None:
    limit = None if all_items else 10
    try:
        releases = list_user_release_cards(user_id, limit=limit)
    except Exception as exc:
        logger.error("Could not load releases for user %s: %s", user_id, exc)
        text = "❌ Ошибка при получении релизов."
        if edit_message_id is None:
            bot.send_message(chat_id, text)
        else:
            bot.edit_message_text(text, chat_id, edit_message_id)
        return

    text = _releases_text(releases, all_items=all_items)
    markup = _releases_markup(releases, all_items=all_items)
    if edit_message_id is None:
        bot.send_message(chat_id, text, reply_markup=markup)
    else:
        bot.edit_message_text(text, chat_id, edit_message_id, reply_markup=markup)


def register_release_handlers(bot) -> None:
    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "📀 Мои релизы")
    def handle_my_releases(message):
        _send_releases(bot, message.chat.id, message.from_user.id)

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "◀️ Назад к моим релизам")
    def handle_back_to_my_releases_message(message):
        _send_releases(bot, message.chat.id, message.from_user.id)

    @bot.callback_query_handler(func=lambda call: call.data == "profile_releases")
    def handle_profile_releases(call):
        bot.answer_callback_query(call.id)
        _send_releases(bot, call.message.chat.id, call.from_user.id, edit_message_id=call.message.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "all_releases")
    def handle_all_releases(call):
        bot.answer_callback_query(call.id)
        _send_releases(
            bot,
            call.message.chat.id,
            call.from_user.id,
            edit_message_id=call.message.message_id,
            all_items=True,
        )

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_my_releases")
    def handle_back_to_my_releases(call):
        bot.answer_callback_query(call.id)
        _send_releases(bot, call.message.chat.id, call.from_user.id, edit_message_id=call.message.message_id)
