"""Admin promo read-only/menu handlers."""
from __future__ import annotations

import logging
from decimal import Decimal

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.promos import get_admin_promo_stats
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


def _promo_menu_markup(back_callback: str = "admin_finance"):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Создать промокод", callback_data="promo_create"),
        types.InlineKeyboardButton("📊 Статистика промокодов", callback_data="promo_stats"),
        types.InlineKeyboardButton("❌ Удалить промокоды", callback_data="promo_delete"),
        types.InlineKeyboardButton("◀️ Назад", callback_data=back_callback),
    )
    return markup


def _money(value) -> str:
    amount = Decimal(value or 0)
    return f"{amount}₽"


def _promo_stats_text(stats: dict) -> str:
    return (
        "📊 Статистика промокодов\n\n"
        f"Всего промокодов: {stats['total']}\n"
        f"Активных: {stats['active']}\n"
        f"Истекших: {stats['expired']}\n"
        f"С лимитом использований: {stats['limited_usage']}\n"
        f"Общая сумма всех: {_money(stats['total_amount'])}\n"
        f"Сумма использованных: {_money(stats['used_amount'])}"
    )


def _require_admin(bot, call) -> bool:
    if _is_admin(call.from_user.id):
        return True
    bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
    return False


def register_admin_promo_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "finance_promo")
    def handle_finance_promo(call):
        if not _require_admin(bot, call):
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🎟 Управление промокодами",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_promo_menu_markup("admin_finance"),
        )

    @bot.callback_query_handler(func=lambda call: call.data == "promo_stats")
    def handle_promo_stats(call):
        if not _require_admin(bot, call):
            return
        stats = get_admin_promo_stats()
        if not stats:
            bot.answer_callback_query(call.id, "❌ Ошибка получения статистики", show_alert=True)
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="finance_promo"))
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _promo_stats_text(stats),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
