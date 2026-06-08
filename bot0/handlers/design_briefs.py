"""Design brief capture callbacks for paid visual services."""
from __future__ import annotations

import logging
from typing import Any, Callable

from telebot import types

logger = logging.getLogger(__name__)

bot = None
DESIGN_BRIEF_TEMPLATES: dict[str, dict[str, Any]] = {}
ensure_user_storage: Callable[[int], dict] | None = None
is_cancel_message: Callable[..., bool] | None = None


def configure_design_briefs(**context: Any) -> None:
    globals().update({key: value for key, value in context.items() if value is not None})


def _require(name: str) -> Any:
    value = globals().get(name)
    if value is None:
        raise RuntimeError(f"design brief dependency is not configured: {name}")
    return value


def prompt_design_brief(user_id, service):
    active_bot = _require("bot")
    template = DESIGN_BRIEF_TEMPLATES.get(service)
    if not template:
        return

    instructions = [
        f"📝 {template['title']}",
        "Пожалуйста, отправьте одним сообщением данные по шаблону ниже:",
        "",
    ]
    for field in template["fields"]:
        instructions.append(f"{field}: ...")
    if template.get("note"):
        instructions.extend(["", template["note"]])
    instructions.append("")
    instructions.append("После отправки брифа вы сможете оплатить услугу.")

    try:
        msg = active_bot.send_message(user_id, "\n".join(instructions))
        active_bot.register_next_step_handler(msg, process_design_brief, service)
    except Exception as exc:
        logger.error("Failed to send design brief prompt to %s: %s", user_id, exc)


def process_design_brief(message, service):
    active_bot = _require("bot")
    if not getattr(message, "text", None):
        active_bot.reply_to(message, "Пожалуйста, отправьте текстовое описание брифа.")
        prompt_design_brief(message.chat.id, service)
        return

    cancel_check = is_cancel_message
    if cancel_check and cancel_check(message):
        active_bot.reply_to(message, "🚫 Отправка брифа отменена.")
        return

    storage = _require("ensure_user_storage")(message.from_user.id)
    briefs = storage.setdefault("design_briefs", {})
    briefs[service] = message.text.strip()

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💳 Оплатить", callback_data=f"pay_{service}"))
    active_bot.reply_to(
        message,
        "✅ Бриф сохранён! Теперь нажмите «Оплатить», чтобы отправить заказ.",
        reply_markup=markup,
    )


def register_design_brief_handlers(bot, context: dict | None = None) -> None:
    configure_design_briefs(bot=bot, **(context or {}))

    @bot.callback_query_handler(func=lambda call: (getattr(call, "data", "") or "").startswith("design_brief_"))
    def handle_design_brief_request(call):
        service = call.data.split("_", 2)[2]
        if service not in DESIGN_BRIEF_TEMPLATES:
            bot.answer_callback_query(call.id, "Шаблон недоступен.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        prompt_design_brief(call.from_user.id, service)
