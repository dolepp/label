"""Order history handlers for the modular bot."""
from __future__ import annotations

import logging
from typing import Any

from telebot import types

from db.repositories.orders import count_user_orders, format_amount, format_order_datetime, list_user_orders


logger = logging.getLogger(__name__)

SERVICE_LABELS = {
    "topup": "Пополнение баланса",
    "cover": "Обложка",
    "motion": "Motion-обложка",
    "videoshot": "Видеошот",
    "distribution": "Дистрибуция",
    "other": "Другое",
}

STATUS_LABELS = {
    "pending": "⏳ ожидает",
    "completed": "✅ выполнен",
    "cancelled": "🚫 отменен",
    "failed": "❌ ошибка",
}


def _back_markup(include_topup: bool = False):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if include_topup:
        markup.add(types.InlineKeyboardButton("💳 Пополнить баланс", callback_data="topup_from_profile"))
    markup.add(types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile"))
    return markup


def _orders_markup(total: int, shown: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if total > shown:
        markup.add(types.InlineKeyboardButton(f"🛍 Показать все ({total})", callback_data="all_orders"))
    markup.add(types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile"))
    return markup


def _order_line(index: int, order: dict[str, Any]) -> str:
    service = SERVICE_LABELS.get(order["service_type"], order["service_type"])
    status = STATUS_LABELS.get(order["status"], order["status"])
    date = format_order_datetime(order["created_date"])
    amount = format_amount(order["amount"])
    return f"{index}. Заказ #{order['id']} - {service} - {amount} - {status} ({date})"


def _orders_text(orders: list[dict[str, Any]], title: str = "🛒 Ваши заказы") -> str:
    lines = [f"{title}:\n"]
    for index, order in enumerate(orders, 1):
        lines.append(_order_line(index, order))
    return "\n".join(lines)


def _send_orders(bot, chat_id: int, user_id: int, limit: int = 10, edit_message_id: int | None = None) -> None:
    total = count_user_orders(user_id)
    if total is None:
        if edit_message_id is None:
            bot.send_message(chat_id, "❌ Ошибка подключения к базе данных.")
        else:
            bot.edit_message_text("❌ Ошибка подключения к базе данных.", chat_id, edit_message_id)
        return

    orders = list_user_orders(user_id, limit=limit)
    if not orders:
        text = "🛒 У вас пока нет заказов\n\nПополните баланс или выберите услугу."
        markup = _back_markup(include_topup=True)
    else:
        text = _orders_text(orders)
        markup = _orders_markup(total, len(orders))

    if edit_message_id is None:
        bot.send_message(chat_id, text, reply_markup=markup)
    else:
        bot.edit_message_text(text, chat_id, edit_message_id, reply_markup=markup)


def register_order_handlers(bot) -> None:
    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "🛒 Мои заказы")
    def handle_my_orders(message):
        _send_orders(bot, message.chat.id, message.from_user.id)

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "🛍 Мои заказы")
    def handle_my_orders_alt(message):
        _send_orders(bot, message.chat.id, message.from_user.id)

    @bot.callback_query_handler(func=lambda call: call.data == "profile_orders")
    def handle_profile_orders(call):
        bot.answer_callback_query(call.id)
        _send_orders(bot, call.message.chat.id, call.from_user.id, edit_message_id=call.message.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "all_orders")
    def handle_all_orders(call):
        bot.answer_callback_query(call.id)
        _send_orders(bot, call.message.chat.id, call.from_user.id, limit=50, edit_message_id=call.message.message_id)
