"""User booking handlers for modular bot code."""
from __future__ import annotations

import logging

from telebot import types

from db.repositories.bookings import format_booking_date, list_user_bookings


logger = logging.getLogger(__name__)


def _booking_line(index: int, booking: dict) -> str:
    return (
        f"{index}. Запись #{booking['id']} "
        f"({format_booking_date(booking['booking_date'])}) - {booking['status'] or 'статус не указан'}"
    )


def _bookings_text(bookings: list[dict]) -> str:
    if not bookings:
        return "🎧 У вас пока нет записей\n\nСейчас раздел записи на студию не настроен."
    return "🎧 Ваши записи:\n\n" + "\n".join(_booking_line(index, booking) for index, booking in enumerate(bookings, 1))


def _bookings_markup(has_bookings: bool):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if has_bookings:
        markup.add(types.InlineKeyboardButton("🎧 Все записи", callback_data="all_bookings"))
    markup.add(types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile"))
    return markup


def _send_bookings(bot, call, limit: int | None = 10) -> None:
    try:
        bookings = list_user_bookings(call.from_user.id, limit=limit)
    except Exception as exc:
        logger.error("Could not load bookings for user %s: %s", call.from_user.id, exc)
        bot.answer_callback_query(call.id, "❌ Ошибка при получении записей", show_alert=True)
        return

    bot.answer_callback_query(call.id)
    bot.edit_message_text(
        _bookings_text(bookings),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=_bookings_markup(bool(bookings)),
    )


def register_booking_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "profile_bookings")
    def handle_profile_bookings(call):
        _send_bookings(bot, call, limit=10)

    @bot.callback_query_handler(func=lambda call: call.data == "all_bookings")
    def handle_all_bookings(call):
        _send_bookings(bot, call, limit=None)
