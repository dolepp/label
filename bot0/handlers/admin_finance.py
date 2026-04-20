"""Admin finance handlers for modular bot code."""
from __future__ import annotations

import logging
from decimal import Decimal

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.admin_finance import calculate_share, get_finance_breakdown
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


def _money(value: Decimal) -> str:
    return f"{value:,.2f}₽"


def _finance_stats_text(stats: dict) -> str:
    total_revenue = Decimal(stats.get("total_revenue") or 0)
    monthly_revenue = Decimal(stats.get("monthly_revenue") or 0)
    today_revenue = Decimal(stats.get("today_revenue") or 0)

    artem_share, remaining_income = calculate_share(total_revenue)
    monthly_artem_share, monthly_remaining = calculate_share(monthly_revenue)
    today_artem_share, today_remaining = calculate_share(today_revenue)

    return (
        "📊 Подробная финансовая статистика\n\n"
        f"💰 Общий доход: {_money(total_revenue)}\n"
        f"👤 Доля Артёма (15%): {_money(artem_share)}\n"
        f"🏢 Оставшийся доход: {_money(remaining_income)}\n\n"
        f"📅 Доход за месяц: {_money(monthly_revenue)}\n"
        f"👤 Доля Артёма за месяц: {_money(monthly_artem_share)}\n"
        f"🏢 Оставшийся доход за месяц: {_money(monthly_remaining)}\n\n"
        f"📆 Доход за сегодня: {_money(today_revenue)}\n"
        f"👤 Доля Артёма за сегодня: {_money(today_artem_share)}\n"
        f"🏢 Оставшийся доход за сегодня: {_money(today_remaining)}"
    )


def _finance_overview_text(stats: dict) -> str:
    total_revenue = Decimal(stats.get("total_revenue") or 0)
    today_revenue = Decimal(stats.get("today_revenue") or 0)
    return (
        "💰 Финансовая статистика\n\n"
        f"Общий доход: {_money(total_revenue)}\n"
        f"Доход за сегодня: {_money(today_revenue)}"
    )


def _finance_overview_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📊 Подробная статистика", callback_data="finance_stats"),
        types.InlineKeyboardButton("💳 История платежей", callback_data="finance_history"),
        types.InlineKeyboardButton("🎟 Управление промокодами", callback_data="finance_promo"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"),
    )
    return markup


def _back_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_finance"))
    return markup


def register_admin_finance_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "admin_finance")
    def handle_admin_finance(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        stats = get_finance_breakdown()
        if not stats:
            bot.edit_message_text(
                "❌ Ошибка подключения к базе данных. Попробуйте позже.",
                call.message.chat.id,
                call.message.message_id,
            )
            return

        bot.edit_message_text(
            _finance_overview_text(stats),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_finance_overview_markup(),
        )

    @bot.callback_query_handler(func=lambda call: call.data == "finance_stats")
    def handle_finance_stats(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        stats = get_finance_breakdown()
        if not stats:
            bot.edit_message_text(
                "❌ Ошибка подключения к базе данных. Попробуйте позже.",
                call.message.chat.id,
                call.message.message_id,
            )
            return

        bot.edit_message_text(
            _finance_stats_text(stats),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_back_markup(),
        )
