"""Reusable ReplyKeyboardMarkup builders for modular handlers."""
from telebot import types


MAIN_MENU_BUTTONS = (
    "🎵 Наши услуги",
    "👤 Мой профиль",
    "⭐️ Отзывы",
    "❓ Помощь/вопросы",
    "🌐 Открыть приложение",
    "📞 Поддержка",
)

PROFILE_MENU_ROWS = (
    ("✏️ Редактировать профиль", "📀 Мои релизы"),
    ("📋 Черновики", "📊 Мои отчеты"),
    ("🆘 Мои заявки", "🛒 Мои заказы"),
    ("💳 Пополнить баланс", "🎟 Ввести промокод"),
    ("👥 Пригласи друга", "◀️ Назад в меню"),
)


def create_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(*(types.KeyboardButton(text) for text in MAIN_MENU_BUTTONS))
    return markup


def create_profile_menu(include_referral: bool = True):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for row in PROFILE_MENU_ROWS:
        if not include_referral and "👥 Пригласи друга" in row:
            markup.add(types.KeyboardButton("◀️ Назад в меню"))
            continue
        markup.add(*(types.KeyboardButton(text) for text in row))
    return markup


def create_profile_edit_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🎤 Изменить имя артиста"),
        types.KeyboardButton("📺 Изменить канал"),
        types.KeyboardButton("👥 Изменить ФИО"),
        types.KeyboardButton("📧 Изменить email"),
        types.KeyboardButton("◀️ Назад в профиль"),
    )
    return markup


def create_cancel_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("❌ Отмена"))
    return markup

def create_options_keyboard(options):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [types.KeyboardButton(opt) for opt in options]
    markup.add(*buttons)
    markup.add(types.KeyboardButton("❌ Отмена"))
    return markup
