"""Finance profile handlers for the modular bot."""
from __future__ import annotations

import logging
from decimal import Decimal

from telebot import types

from db.repositories.finance import get_user_finance_summary


logger = logging.getLogger(__name__)


def _money(value) -> str:
    amount = Decimal(value or 0)
    return f"{amount:,.2f}".replace(",", " ")


def _finance_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("💳 Пополнить", callback_data="topup_from_profile"))
    markup.add(types.InlineKeyboardButton("🎟 Промокод", callback_data="promo_from_profile"))
    markup.add(types.InlineKeyboardButton("🛒 Мои заказы", callback_data="profile_orders"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_profile"))
    return markup


def _finance_text(summary: dict) -> str:
    return (
        "💰 Ваши финансы:\n\n"
        f"💳 Баланс: {_money(summary['balance'])}₽\n"
        f"📊 Всего заказов: {summary['total_orders']}\n"
        f"✅ Завершенных: {summary['completed_orders']}\n"
        f"⏳ Ожидают оплаты: {summary['pending_orders']}\n"
        f"🚫 Отмененных: {summary['cancelled_orders']}\n"
        f"💵 Оплачено всего: {_money(summary['completed_sum'])}₽"
    )


def register_finance_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "profile_finance")
    def handle_profile_finance(call):
        summary = get_user_finance_summary(call.from_user.id)
        if summary is None:
            bot.answer_callback_query(call.id, "❌ Финансовая информация не найдена", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _finance_text(summary),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_finance_markup(),
        )
