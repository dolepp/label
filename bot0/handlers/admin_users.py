"""Admin user list handlers."""
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
    name = user.get("name")
    username = user.get("tg")
    if name and username:
        return f"{name} (@{username})"
    return f"ID: {user['telegram_id']}"


def _admin_users_text(users: list[dict]) -> str:
    return (
        f"👥 Список всех пользователей ({len(users)})\n\n"
        "📋 Для каждого пользователя доступно:\n"
        "• 🔧 Управление ролями\n"
        "• 📊 Просмотр запросов отчетов\n\n"
        "💡 Быстрый доступ:\n"
        "• 📊 Запросы отчетов - все отчеты в одном месте\n"
        "• 📋 Управление договорами - загрузка готовых договоров\n\n"
        "Выберите пользователя для управления:"
    )


def _admin_users_markup(users: list[dict]):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for index, user in enumerate(users):
        user_id = user["telegram_id"]
        markup.row(types.InlineKeyboardButton(_display_name(user), callback_data=f"user_info_{user_id}"))
        markup.row(
            types.InlineKeyboardButton("🔧 Управление ролью", callback_data=f"user_role_{user_id}"),
            types.InlineKeyboardButton("📊 Запросы отчетов", callback_data=f"user_reports_{user_id}"),
        )
        if index < len(users) - 1:
            markup.row(types.InlineKeyboardButton("━━━━━━━━━━━━━━━━━━━━", callback_data="separator"))

    markup.add(
        types.InlineKeyboardButton("📊 Запросы отчетов", callback_data="admin_report_requests"),
        types.InlineKeyboardButton("📋 Управление договорами", callback_data="admin_contracts"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"),
    )
    return markup


def _empty_users_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))
    return markup


def register_admin_user_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "admin_users")
    def handle_admin_users(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
            return

        try:
            users = list_admin_user_cards()
        except Exception as exc:
            logger.error("PostgreSQL error in handle_admin_users: %s", exc)
            bot.answer_callback_query(
                call.id,
                "❌ Произошла ошибка при получении списка пользователей.",
                show_alert=True,
            )
            return

        if not users:
            bot.edit_message_text(
                "🤷‍♀️ В базе данных нет зарегистрированных пользователей.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=_empty_users_markup(),
            )
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _admin_users_text(users),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_admin_users_markup(users),
        )

