"""Small shared callback handlers."""
from __future__ import annotations


def register_common_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "separator")
    def handle_separator(call):
        bot.answer_callback_query(call.id, "", show_alert=False)

