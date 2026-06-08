"""Small shared callback handlers."""
from __future__ import annotations

from keyboards.reply import create_main_menu


def register_common_handlers(bot) -> None:
    @bot.message_handler(commands=["cancel"])
    def handle_cancel_command(message):
        user_id = message.from_user.id
        user_data = getattr(bot, "user_data", {})
        if user_id in user_data:
            for key in list(user_data[user_id].keys()):
                if key != "pending_operation":
                    user_data[user_id].pop(key, None)
        bot.send_message(message.chat.id, "❌ Процесс создания релиза отменён.", reply_markup=create_main_menu())

    @bot.callback_query_handler(func=lambda call: call.data == "separator")
    def handle_separator(call):
        bot.answer_callback_query(call.id, "", show_alert=False)

