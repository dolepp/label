"""Инлайн-клавиатуры для бота."""
from telebot import types

def create_services_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🎨 Обложка (500₽)", callback_data="service_cover"),
        types.InlineKeyboardButton("🎬 Motion (800₽)", callback_data="service_motion"),
        types.InlineKeyboardButton("📹 Видеошот (1000₽)", callback_data="service_videoshot"),
        types.InlineKeyboardButton("🎵 Дистрибуция (1299₽)", callback_data="service_distribution"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu")
    )
    return markup

def create_admin_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📋 Релизы", callback_data="admin_releases"),
        types.InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
        types.InlineKeyboardButton("💰 Финансы", callback_data="admin_finance"),
        types.InlineKeyboardButton("📞 Поддержка", callback_data="admin_support")
    )
    return markup

def create_profile_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✏️ Редактировать", callback_data="edit_profile"),
        types.InlineKeyboardButton("📝 Черновики", callback_data="profile_drafts"),
        types.InlineKeyboardButton("💰 Баланс", callback_data="view_balance"),
        types.InlineKeyboardButton("🎵 Релизы", callback_data="my_releases"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="main_menu")
    )
    return markup
