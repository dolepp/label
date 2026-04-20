"""Admin statistics handlers."""
from __future__ import annotations

import logging
from decimal import Decimal

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.admin_stats import get_admin_stats
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


def _admin_stats_text(stats: dict) -> str:
    total_revenue = Decimal(stats.get("total_revenue") or 0)
    return (
        "📊 Статистика TWAS Label\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"📀 Отгруженных релизов: {stats['total_releases']}\n"
        f"🎧 Записей в студии: {stats['total_bookings']}\n"
        f"💰 Общий оборот: {total_revenue:,.2f}₽\n"
        f"⭐️ Отзывов: {stats['total_reviews']}\n"
        f"📈 Новых пользователей за неделю: {stats['new_users_week']}\n"
    )


def _admin_stats_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    for text, callback in (("За неделю", "stats_week"), ("За месяц", "stats_month"), ("За все время", "stats_all")):
        markup.add(types.InlineKeyboardButton(text, callback_data=callback))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))
    return markup


def register_admin_stats_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "admin_stats")
    def handle_admin_stats(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
            return

        stats = get_admin_stats()
        if not stats:
            bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _admin_stats_text(stats),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_admin_stats_markup(),
        )
