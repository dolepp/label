"""Admin user detail read-only handlers."""
from __future__ import annotations

import logging
from decimal import Decimal

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.admin_user_info import get_admin_user_info
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


def _admin_user_info_text(user: dict) -> str:
    created_date = user.get("created_date")
    balance = Decimal(user.get("balance") or 0)
    return (
        "👤 Информация о пользователе\n\n"
        f"Имя: {user.get('name') or 'Не указано'}\n"
        f"Username: @{user.get('tg') or 'Не указан'}\n"
        f"ID: {user['telegram_id']}\n"
        "Роли:\n"
        f"• Администратор: {'Да' if user.get('admin') else 'Нет'}\n"
        f"• Артист: {'Да' if user.get('artist') else 'Нет'}\n"
        f"• Owner: {'Да' if user.get('owner') else 'Нет'}\n"
        f"• Creator: {'Да' if user.get('creator') else 'Нет'}\n"
        f"Баланс: {balance}₽\n"
        f"Дата регистрации: {created_date.strftime('%d.%m.%Y') if created_date else 'Не указана'}\n"
        f"Email: {user.get('email') or 'Не указан'}\n"
        f"ФИО: {user.get('fio') or 'Не указано'}\n"
        f"Телефон: {user.get('phone') or 'Не указан'}\n"
        f"Количество релизов: {user.get('releases_count', 0)}"
    )


def _admin_user_info_markup(user_id: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🔧 Управление ролями", callback_data=f"user_role_{user_id}"))
    markup.add(types.InlineKeyboardButton("📀 Релизы пользователя", callback_data=f"user_releases_{user_id}"))
    markup.add(types.InlineKeyboardButton("◀️ К списку пользователей", callback_data="admin_users"))
    markup.add(types.InlineKeyboardButton("◀️ В админ панель", callback_data="admin_back"))
    return markup


def register_admin_user_info_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data.startswith(("user_info_", "user_detail_")))
    def handle_user_info(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
            return

        try:
            user_id = int(call.data.split("_")[2])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return

        try:
            user = get_admin_user_info(user_id)
        except Exception as exc:
            logger.error("Error showing user info: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return

        if not user:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден", show_alert=True)
            return

        text = _admin_user_info_text(user)
        if len(text) > 4000:
            text = text[:4000] + "..."

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_admin_user_info_markup(user_id),
        )

