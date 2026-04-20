"""Balance top-up UI handlers.

Payment provider creation callbacks remain in the legacy monolith.
"""
from __future__ import annotations

import re

from telebot import types


TOPUP_AMOUNTS = (300, 500, 1000, 2000)


def _topup_text() -> str:
    return "💳 Пополнение баланса\n\nВыберите сумму:"


def _amount_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    for amount in TOPUP_AMOUNTS:
        markup.add(types.InlineKeyboardButton(f"{amount}₽", callback_data=f"topup_{amount}"))
    markup.add(types.InlineKeyboardButton("Другая сумма", callback_data="topup_custom"))
    markup.add(types.InlineKeyboardButton("◀️ Отмена", callback_data="back_to_profile"))
    return markup


def _payment_method_markup(amount: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💳 YooKassa", callback_data=f"yookassa_pay_{amount}"),
        types.InlineKeyboardButton("🤖 Crypto Bot", callback_data=f"crypto_pay_{amount}"),
        types.InlineKeyboardButton("⭐ Telegram Stars", callback_data=f"stars_pay_{amount}"),
        types.InlineKeyboardButton("💎 TON", callback_data=f"ton_pay_{amount}"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="topup_back"),
    )
    return markup


def _parse_amount(text: str) -> int | None:
    try:
        amount = int(re.sub(r"[^0-9]", "", text or ""))
        return amount if amount > 0 else None
    except Exception:
        return None


def _send_amount_menu(bot, chat_id: int, message_id: int | None = None) -> None:
    if message_id is None:
        bot.send_message(chat_id, _topup_text(), reply_markup=_amount_markup())
        return
    try:
        bot.edit_message_text(_topup_text(), chat_id, message_id, reply_markup=_amount_markup())
    except Exception:
        bot.send_message(chat_id, _topup_text(), reply_markup=_amount_markup())


def _send_payment_methods(bot, call, amount: int) -> None:
    text = f"💰 Пополнение баланса на {amount}₽\n\nВыберите способ оплаты:"
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=_payment_method_markup(amount))
    except Exception:
        bot.send_message(call.message.chat.id, text, reply_markup=_payment_method_markup(amount))


def register_topup_handlers(bot) -> None:
    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "💳 Пополнить баланс")
    def handle_topup_request(message):
        bot.reply_to(message, _topup_text(), reply_markup=_amount_markup())

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith("topup_")
        and not call.data.startswith("topup_pay_")
        and call.data not in ("topup_back", "topup_from_profile")
    )
    def handle_topup_callback(call):
        bot.answer_callback_query(call.id)
        if call.data == "topup_custom":
            bot.edit_message_text("Введите сумму пополнения (целое число рублей):", call.message.chat.id, call.message.message_id)
            bot.register_next_step_handler(call.message, process_custom_topup_amount)
            return
        amount = int(call.data.split("_")[1])
        _send_payment_methods(bot, call, amount)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("topup_pay_"))
    def handle_topup_pay(call):
        bot.answer_callback_query(call.id)
        amount = int(call.data.split("_")[2])
        _send_payment_methods(bot, call, amount)

    @bot.callback_query_handler(func=lambda call: call.data == "topup_back")
    def handle_topup_back(call):
        bot.answer_callback_query(call.id)
        _send_amount_menu(bot, call.message.chat.id, call.message.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "topup_from_profile")
    def handle_topup_from_profile(call):
        bot.answer_callback_query(call.id)
        _send_amount_menu(bot, call.message.chat.id, call.message.message_id)

    def process_custom_topup_amount(message):
        amount = _parse_amount(getattr(message, "text", ""))
        if amount is None:
            sent = bot.reply_to(message, "❌ Неверная сумма. Введите положительное число, например: 500")
            bot.register_next_step_handler(sent, process_custom_topup_amount)
            return

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Перейти к оплате", callback_data=f"topup_pay_{amount}"))
        bot.send_message(message.chat.id, f"К оплате: {amount}₽", reply_markup=markup)
