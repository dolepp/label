"""Admin release management entry handlers."""
from __future__ import annotations

import logging

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.admin_users import list_admin_user_cards
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

