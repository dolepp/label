"""Admin callbacks for design/service orders."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from telebot import types

from db.repositories.admins import ensure_admin_access
from db.repositories.design_orders import (
    count_design_orders_by_service,
    get_design_order,
    list_design_orders,
    update_design_order_status,
)

logger = logging.getLogger(__name__)

bot = None
DESIGN_ORDER_STATUSES = ["принят", "в работе", "готов", "требует уточнения"]
DESIGN_BRIEF_TEMPLATES: dict[str, dict[str, Any]] = {}
DESIGN_BRIEF_REQUESTS: list[dict[str, Any]] = []
SERVICE_TITLES = {"cover": "🎨 Обложки", "motion": "🎬 Motion", "videoshot": "📹 Видеошоты"}


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


def _find_order(request_id):
    """Заказ из БД; список в памяти — только для заказов, созданных до перехода на БД."""
    try:
        order = get_design_order(request_id)
    except Exception as exc:
        logger.error("Could not load design order %s: %s", request_id, exc)
        order = None
    if order:
        return order
    return next((req for req in DESIGN_BRIEF_REQUESTS if str(req["id"]) == str(request_id)), None)


def _is_admin(call) -> bool:
    try:
        return bool(ensure_admin_access(call.from_user.id, getattr(call.from_user, "username", None)).get("allowed"))
    except Exception as exc:
        logger.error("Could not check admin access for %s: %s", call.from_user.id, exc)
        return False


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

    if not _is_admin(call):
        active_bot.answer_callback_query(call.id, "❌ Нет доступа", show_alert=True)
        return

    order = _find_order(request_id)
    if not order:
        active_bot.answer_callback_query(call.id, "Заказ не найден", show_alert=True)
        return

    try:
        updated = update_design_order_status(request_id, new_status)
    except Exception as exc:
        logger.error("Could not update design order %s: %s", request_id, exc)
        updated = None
    order = updated or order
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
    if not _is_admin(call):
        active_bot.answer_callback_query(call.id, "❌ Нет доступа", show_alert=True)
        return
    order = _find_order(request_id)
    if not order:
        active_bot.answer_callback_query(call.id, "Заказ не найден", show_alert=True)
        return

    text = format_design_request_text(order)
    markup = build_design_status_markup(request_id, order["status"])
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"admin_orders_{order['service']}"))
    active_bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)


def show_orders_overview(call):
    active_bot = _require_bot()
    if not _is_admin(call):
        active_bot.answer_callback_query(call.id, "❌ Нет доступа", show_alert=True)
        return
    try:
        counts = count_design_orders_by_service()
        recent = list_design_orders(limit=5)
    except Exception as exc:
        logger.error("Could not load design orders: %s", exc)
        active_bot.answer_callback_query(call.id, "❌ Ошибка загрузки заказов", show_alert=True)
        return
    lines = ["🛒 Заказы дизайна\n"]
    for service, title in SERVICE_TITLES.items():
        lines.append(f"{title}: {counts.get(service, 0)}")
    if recent:
        lines.append("\nПоследние:")
        for order in recent:
            lines.append(f"• #{order['id']} {SERVICE_TITLES.get(order['service'], order['service'])} — {order['user_display']} — {order['status']} ({_format_human_datetime(order['created_at'])})")
    else:
        lines.append("\nЗаказов пока нет.")
    lines.append("\nЗаказы с сайта — в веб-админке, раздел «Финансы».")
    markup = types.InlineKeyboardMarkup(row_width=1)
    for service, title in SERVICE_TITLES.items():
        markup.add(types.InlineKeyboardButton(title, callback_data=f"admin_orders_{service}"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))
    active_bot.answer_callback_query(call.id)
    active_bot.edit_message_text("\n".join(lines), call.message.chat.id, call.message.message_id, reply_markup=markup)


def show_orders_list(call, service):
    active_bot = _require_bot()
    if not _is_admin(call):
        active_bot.answer_callback_query(call.id, "❌ Нет доступа", show_alert=True)
        return
    try:
        orders = list_design_orders(service=service, limit=10)
    except Exception as exc:
        logger.error("Could not load design orders for %s: %s", service, exc)
        active_bot.answer_callback_query(call.id, "❌ Ошибка загрузки заказов", show_alert=True)
        return
    title = SERVICE_TITLES.get(service, service)
    text = f"{title} — последние заявки:" if orders else f"{title}: заказов пока нет."
    markup = types.InlineKeyboardMarkup(row_width=1)
    for order in orders:
        markup.add(types.InlineKeyboardButton(
            f"#{order['id']} · {order['status']} · {order['user_display']}",
            callback_data=f"order_detail_{order['id']}",
        ))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_orders"))
    active_bot.answer_callback_query(call.id)
    active_bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)


def register_design_admin_handlers(bot, context: dict | None = None) -> None:
    configure_design_admin(bot=bot, **(context or {}))

    @bot.callback_query_handler(func=lambda call: (getattr(call, "data", "") or "").startswith("design_status:"))
    def design_status_callback(call):
        handle_design_status_change(call)

    @bot.callback_query_handler(func=lambda call: (getattr(call, "data", "") or "") == "admin_orders")
    def admin_orders_callback(call):
        show_orders_overview(call)

    @bot.callback_query_handler(func=lambda call: (getattr(call, "data", "") or "").startswith("admin_orders_"))
    def admin_orders_service_callback(call):
        show_orders_list(call, call.data.replace("admin_orders_", "", 1))

    @bot.callback_query_handler(func=lambda call: (getattr(call, "data", "") or "").startswith("order_detail_"))
    def order_detail_callback(call):
        request_id = call.data.split("_", 2)[2]
        show_order_detail(call, request_id)
