# -*- coding: utf-8 -*-
"""Клавиатура профиля."""
from telebot import types

def create_profile_menu():
    """Create profile menu keyboard"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("📝 Мои данные", "profile_data"),
        ("💰 Мои финансы", "profile_finance"),
        ("📀 Мои релизы", "profile_releases"),
        ("📋 Черновики", "profile_drafts"),
        ("🎧 Мои записи", "profile_bookings"),
        ("🛍 Мои заказы", "profile_orders"),
        ("👥 Пригласи друга", "profile_referral")
    ]

    for text, callback in buttons:
        markup.add(types.InlineKeyboardButton(text, callback_data=callback))

    return markup
