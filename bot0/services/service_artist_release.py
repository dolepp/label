"""Admin entry point for creating a release on behalf of an artist."""
from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

bot = None
is_admin: Callable[[int], bool] | None = None
process_artist_user_id: Callable[..., Any] | None = None


def configure(**context: Any) -> None:
    globals().update({key: value for key, value in context.items() if value is not None})


def _require(name: str) -> Any:
    value = globals().get(name)
    if value is None:
        raise RuntimeError(f"artist-release service dependency is not configured: {name}")
    return value


def handle_service_release_for_artist(call):
    active_bot = _require("bot")
    if not _require("is_admin")(call.from_user.id):
        active_bot.answer_callback_query(call.id, "❌ Эта функция доступна только администраторам", show_alert=True)
        return

    active_bot.edit_message_text(
        "📤 Выгрузка релиза за артиста\n\n"
        "Введите Telegram ID пользователя, для которого нужно создать релиз:\n\n"
        "💡 Можно найти ID пользователя в админ-панели → Пользователи",
        call.message.chat.id,
        call.message.message_id,
    )
    active_bot.register_next_step_handler(call.message, _require("process_artist_user_id"))
