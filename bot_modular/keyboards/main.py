# -*- coding: utf-8 -*-
"""Главное меню бота."""
from telebot import types

def create_main_menu():
    """Create main menu keyboard"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        "🎵 Наши услуги",
        "👤 Мой профиль",
        "⭐️ Отзывы",
        "❓ Помощь/вопросы",
        "🌐 Открыть приложение"
    ]
    markup.add(*[types.KeyboardButton(btn) for btn in buttons])
    return markup
