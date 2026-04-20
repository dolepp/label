"""Admin user role read-only menu handlers."""
from __future__ import annotations

import logging

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.admin_user_roles import get_user_roles
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


def _role_text(value, title: str) -> str:
    return f"{'✅' if value else '❌'} {title}"


def _user_role_text(user: dict) -> str:
    return (
        "🔧 Управление ролями пользователя\n\n"
        f"Пользователь: {_display_name(user)}\n"
        "Текущие роли:\n"
        f"• Администратор: {'Да' if user.get('admin') else 'Нет'}\n"
        f"• Артист: {'Да' if user.get('artist') else 'Нет'}\n"
        f"• Owner: {'Да' if user.get('owner') else 'Нет'}\n"
        f"• Creator: {'Да' if user.get('creator') else 'Нет'}\n\n"
        "Нажмите на роль для изменения:"
    )


def _user_role_markup(user: dict):
    user_id = user["telegram_id"]
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(_role_text(user.get("admin"), "Администратор"), callback_data=f"toggle_admin_{user_id}"))
    markup.add(types.InlineKeyboardButton(_role_text(user.get("artist"), "Артист"), callback_data=f"toggle_artist_{user_id}"))
    markup.add(types.InlineKeyboardButton(_role_text(user.get("owner"), "Owner"), callback_data=f"toggle_owner_{user_id}"))
    markup.add(types.InlineKeyboardButton(_role_text(user.get("creator"), "Creator"), callback_data=f"toggle_creator_{user_id}"))
    markup.add(types.InlineKeyboardButton("◀️ К списку пользователей", callback_data="admin_users"))
    markup.add(types.InlineKeyboardButton("◀️ В админ панель", callback_data="admin_back"))
    return markup


def register_admin_user_role_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data.startswith("user_role_"))
    def handle_user_role_management(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
            return

        try:
            user_id = int(call.data.split("_")[2])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return

        try:
            user = get_user_roles(user_id)
        except Exception as exc:
            logger.error("Error in user role management: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return

        if not user:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _user_role_text(user),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_user_role_markup(user),
        )

