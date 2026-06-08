"""User service-selection callbacks."""
from __future__ import annotations

import logging
from typing import Any, Callable

from telebot import types

logger = logging.getLogger(__name__)

bot = None
handle_service_release_for_artist: Callable[..., Any] | None = None

DESIGN_SERVICES = {
    "cover": {
        "name": "Обложка",
        "price": 2000,
        "description": "Профессиональный дизайн обложки для вашего релиза",
    },
    "motion": {
        "name": "Motion обложка",
        "price": 1500,
        "description": "Анимированная обложка для соцсетей",
    },
    "videoshot": {
        "name": "Видеошот",
        "price": 1000,
        "description": "Короткий вертикальный клип",
    },
}


def configure_service_selection(**context: Any) -> None:
    globals().update({key: value for key, value in context.items() if value is not None})


def _service_selection_callback(call) -> bool:
    data = getattr(call, "data", "") or ""
    return data in {"service_cover", "service_motion", "service_videoshot", "service_release_for_artist"}


def show_design_service(message, service_type):
    """Show design service information."""
    active_bot = bot
    if active_bot is None:
        raise RuntimeError("service selection bot is not configured")
    service = DESIGN_SERVICES[service_type]
    service_text = (
        f"🎨 {service['name']}\n\n"
        f"{service['description']}\n\n"
        f"💰 Стоимость: {service['price']}₽\n\n"
        "Перед оплатой заполните бриф — одним сообщением по шаблону.\n"
        "После оплаты заказ появится в админ-панели и менеджер свяжется с вами."
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("📝 Заполнить бриф", callback_data=f"design_brief_{service_type}"),
        types.InlineKeyboardButton("💳 Оплатить", callback_data=f"pay_{service_type}"),
    )
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="services_back"))
    active_bot.edit_message_text(service_text, message.chat.id, message.message_id, reply_markup=markup)


def register_service_selection_handlers(bot, context: dict | None = None) -> None:
    configure_service_selection(bot=bot, **(context or {}))

    @bot.callback_query_handler(func=_service_selection_callback)
    def handle_service_selection(call):
        service = call.data.split("_", 1)[1]
        if service in DESIGN_SERVICES:
            show_design_service(call.message, service)
            return
        if call.data == "service_release_for_artist":
            if handle_service_release_for_artist is None:
                bot.answer_callback_query(call.id, "❌ Обработчик недоступен", show_alert=True)
                return
            handle_service_release_for_artist(call)
