"""Profile handlers for the modular bot."""
from __future__ import annotations

import logging
import re

from telebot import types

from core.config import CHANNEL_USERNAME
from db.repositories.profile import get_profile, update_profile_field
from keyboards.reply import create_main_menu, create_profile_edit_menu, create_profile_menu


logger = logging.getLogger(__name__)

FIELD_LABELS = {
    "name": "имя артиста",
    "kanal": "канал",
    "fio": "ФИО",
    "email": "email",
    "phone": "телефон",
}


def _profile_markup():
    return create_profile_menu()


def _edit_markup():
    return create_profile_edit_menu()


def _main_markup():
    return create_main_menu()


def _profile_text(profile: dict | None) -> str:
    if not profile:
        return "❌ Ваш профиль не найден в базе данных"
    return (
        "👤 Мой профиль:\n\n"
        f"🎤 Имя артиста: {profile.get('name') or 'Не указано'}\n"
        f"📺 Канал: {profile.get('kanal') or 'Не указан'}\n"
        f"👥 ФИО: {profile.get('fio') or 'Не указано'}\n"
        f"📧 Email: {profile.get('email') or 'Не указан'}\n"
        f"📱 Телефон: {profile.get('phone') or 'Не указан'}\n"
        f"💰 Баланс: {float(profile.get('balance') or 0):,.2f}₽"
    )


def _profile_data_text(profile: dict | None) -> str:
    if not profile:
        return "❌ Профиль не найден"
    return (
        "📝 Ваши данные:\n\n"
        f"🎤 Имя артиста: {profile.get('name') or 'Не указано'}\n"
        f"📺 Канал: {profile.get('kanal') or 'Не указан'}\n"
        f"👥 ФИО: {profile.get('fio') or 'Не указано'}\n"
        f"📧 Email: {profile.get('email') or 'Не указан'}\n"
        f"📱 Телефон: {profile.get('phone') or 'Не указан'}\n"
        f"💰 Баланс: {float(profile.get('balance') or 0):,.2f}₽"
    )


def _profile_data_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("✏️ Редактировать", callback_data="edit_profile_data"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_profile"))
    return markup


def _send_profile(bot, chat_id: int, user_id: int) -> None:
    profile = get_profile(user_id)
    bot.send_message(chat_id, _profile_text(profile), reply_markup=_profile_markup())


def _validate_email(value: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$", value))


def _is_subscribed(bot, user_id: int) -> bool:
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as exc:
        logger.error("Could not check channel subscription for user %s: %s", user_id, exc)
        return False


def _require_subscription(bot, message) -> bool:
    if _is_subscribed(bot, message.from_user.id):
        return True
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"),
        types.InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription"),
    )
    bot.reply_to(
        message,
        "🔔 Для использования бота необходимо подписаться на наш канал!",
        reply_markup=markup,
    )
    return False


def register_profile_handlers(bot) -> None:
    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "👤 Мой профиль")
    def handle_profile(message):
        if not _require_subscription(bot, message):
            return
        _send_profile(bot, message.chat.id, message.from_user.id)

    @bot.callback_query_handler(func=lambda call: call.data == "back_to_profile")
    def back_to_profile_handler(call):
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
        _send_profile(bot, call.message.chat.id, call.from_user.id)

    @bot.callback_query_handler(func=lambda call: call.data == "profile_data")
    def handle_profile_data(call):
        profile = get_profile(call.from_user.id)
        if not profile:
            bot.answer_callback_query(call.id, "❌ Профиль не найден", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _profile_data_text(profile),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_profile_data_markup(),
        )

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "✏️ Редактировать профиль")
    def show_profile_edit_options(message):
        bot.reply_to(message, "Выберите, что хотите изменить:", reply_markup=_edit_markup())

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "🎤 Изменить имя артиста")
    def edit_artist_name(message):
        _request_profile_field(message, "name", "Введите новое имя артиста:")

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "📺 Изменить канал")
    def edit_channel(message):
        _request_profile_field(message, "kanal", "Введите новую ссылку на канал:")

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "👥 Изменить ФИО")
    def edit_fio(message):
        _request_profile_field(message, "fio", "Введите новые ФИО:")

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "📧 Изменить email")
    def edit_email(message):
        _request_profile_field(message, "email", "Введите новый email:")

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "📱 Изменить телефон")
    def edit_phone(message):
        _request_profile_field(message, "phone", "Введите номер телефона в формате +79991234567:")

    @bot.callback_query_handler(func=lambda call: call.data == "edit_profile_data")
    def handle_edit_profile_data(call):
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, "Выберите, что хотите изменить:", reply_markup=_edit_markup())

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "◀️ Назад в профиль")
    def back_to_profile(message):
        _send_profile(bot, message.chat.id, message.from_user.id)

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "◀️ Назад в меню")
    def back_to_main_menu(message):
        bot.reply_to(message, "Главное меню:", reply_markup=_main_markup())

    def _request_profile_field(message, field: str, prompt: str) -> None:
        sent = bot.reply_to(message, prompt)
        bot.register_next_step_handler(sent, lambda next_message: _save_profile_field(next_message, field))

    def _save_profile_field(message, field: str) -> None:
        value = (getattr(message, "text", "") or "").strip()
        user_id = message.from_user.id
        if not value:
            sent = bot.reply_to(message, "❌ Значение не может быть пустым. Введите еще раз:")
            bot.register_next_step_handler(sent, lambda next_message: _save_profile_field(next_message, field))
            return
        if field == "phone":
            value = re.sub(r"[\s()-]", "", value)
            if not re.fullmatch(r"\+?\d{10,15}", value):
                sent = bot.reply_to(message, "❌ Неверный формат телефона. Пример: +79991234567")
                bot.register_next_step_handler(sent, lambda next_message: _save_profile_field(next_message, field))
                return
        if field == "email" and not _validate_email(value):
            sent = bot.reply_to(message, "❌ Неверный формат email. Введите действительный email:")
            bot.register_next_step_handler(sent, lambda next_message: _save_profile_field(next_message, field))
            return

        try:
            updated = update_profile_field(user_id, field, value)
        except Exception as exc:
            logger.error("Error updating profile field %s for user %s: %s", field, user_id, exc)
            bot.reply_to(message, "❌ Произошла ошибка при сохранении. Попробуйте позже.")
            return

        if not updated:
            bot.reply_to(message, "❌ Профиль не найден.", reply_markup=_profile_markup())
            return
        bot.reply_to(message, f"✅ {FIELD_LABELS[field].capitalize()} обновлён.", reply_markup=_profile_markup())
