"""Admin callbacks for design/service orders."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from telebot import types

logger = logging.getLogger(__name__)

bot = None
DESIGN_ORDER_STATUSES = ["принят", "в работе", "готов", "требует уточнения"]
DESIGN_BRIEF_TEMPLATES: dict[str, dict[str, Any]] = {}
DESIGN_BRIEF_REQUESTS: list[dict[str, Any]] = []


def configure_design_admin(**context: Any) -> None:
    globals().update({key: value for key, value in context.items() if value is not None})


def _require_bot():
    if bot is None:
        raise RuntimeError("design admin bot is not configured")
    return bot


def _format_human_datetime(value: str) -> str:
    try:
        dt = datetime.fromisoformat(value)
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return value


def build_design_status_markup(request_id, active_status=None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    for status in DESIGN_ORDER_STATUSES:
        prefix = "✅ " if status == active_status else ""
        markup.add(types.InlineKeyboardButton(
            f"{prefix}{status.title()}",
            callback_data=f"design_status:{request_id}:{status}",
        ))
    return markup


def format_design_request_text(order):
    service = DESIGN_BRIEF_TEMPLATES.get(order["service"], {}).get("title", order["service"])
    return (
        f"🎨 Заказ услуги ({service})\n"
        f"Пользователь: {order['user_display']}\n"
        f"Статус: {order['status']}\n"
        f"Создано: {_format_human_datetime(order['created_at'])}\n\n"
        f"Сообщение:\n{order['details']}"
    )


def handle_design_status_change(call):
    active_bot = _require_bot()
    try:
        _, request_id, new_status = call.data.split(":", 2)
    except ValueError:
        active_bot.answer_callback_query(call.id, "Неверные данные", show_alert=True)
        return

    if new_status not in DESIGN_ORDER_STATUSES:
        active_bot.answer_callback_query(call.id, "Недопустимый статус", show_alert=True)
        return

    order = next((req for req in DESIGN_BRIEF_REQUESTS if req["id"] == request_id), None)
    if not order:
        active_bot.answer_callback_query(call.id, "Заказ не найден", show_alert=True)
        return

    order["status"] = new_status
    markup = build_design_status_markup(request_id, new_status)
    text = format_design_request_text(order)

    try:
        active_bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
    except Exception as exc:
        logger.debug("Could not edit admin design message: %s", exc)

    try:
        active_bot.send_message(
            order["chat_id"],
            f"ℹ️ Статус вашего заказа ({DESIGN_BRIEF_TEMPLATES.get(order['service'], {}).get('title', order['service'])}) обновлён: {new_status}.",
        )
    except Exception as exc:
        logger.error("Failed to notify user about design status: %s", exc)

    active_bot.answer_callback_query(call.id, f"Статус изменён на «{new_status}»")


def show_order_detail(call, request_id):
    active_bot = _require_bot()
    order = next((req for req in DESIGN_BRIEF_REQUESTS if req["id"] == request_id), None)
    if not order:
        active_bot.answer_callback_query(call.id, "Заказ не найден", show_alert=True)
        return

    text = format_design_request_text(order)
    markup = build_design_status_markup(request_id, order["status"])
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"admin_orders_{order['service']}"))
    active_bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)


def register_design_admin_handlers(bot, context: dict | None = None) -> None:
    configure_design_admin(bot=bot, **(context or {}))

    @bot.callback_query_handler(func=lambda call: (getattr(call, "data", "") or "").startswith("design_status:"))
    def design_status_callback(call):
        handle_design_status_change(call)

    @bot.callback_query_handler(func=lambda call: (getattr(call, "data", "") or "").startswith("order_detail_"))
    def order_detail_callback(call):
        request_id = call.data.split("_", 2)[2]
        show_order_detail(call, request_id)
