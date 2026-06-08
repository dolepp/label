"""Web authorization command handlers."""
from __future__ import annotations

import logging

from telebot import types

from core.config import WEB_APP_URL
from db.repositories.auth import create_auth_code


logger = logging.getLogger(__name__)


def _auth_text(code: str) -> str:
    return (
        "🔐 **Код для веб-авторизации:**\n\n"
        f"**`{code}`**\n\n"
        "⏰ Код действителен 5 минут\n"
        "🌐 Нажмите кнопку ниже для автоматического входа\n\n"
        f"🔗 Сайт: {WEB_APP_URL}"
    )


def _web_app_markup(user_id: int):
    markup = types.InlineKeyboardMarkup()
    url = f"{WEB_APP_URL}?tgid={user_id}"
    if url.startswith("https://"):
        markup.add(types.InlineKeyboardButton("🌐 Открыть приложение", web_app=types.WebAppInfo(url=url)))
    else:
        markup.add(types.InlineKeyboardButton("🌐 Открыть сайт", url=url))
    return markup


def register_web_auth_handlers(bot) -> None:
    @bot.message_handler(commands=["код", "webauth"])
    def handle_web_auth_code(message):
        user_id = message.from_user.id
        try:
            auth_code = create_auth_code(user_id)
        except Exception as exc:
            logger.error("Could not generate web auth code for user %s: %s", user_id, exc)
            bot.reply_to(message, f"❌ Ошибка генерации кода: {exc}")
            return

        if not auth_code:
            bot.reply_to(message, "❌ Ошибка подключения к базе данных")
            return

        bot.reply_to(
            message,
            _auth_text(auth_code),
            parse_mode="Markdown",
            reply_markup=_web_app_markup(user_id),
        )
