# -*- coding: utf-8 -*-
"""Единый экземпляр бота для модульной версии."""
import telebot
from core.config import BOT_TOKEN

bot = telebot.TeleBot(BOT_TOKEN)
bot.user_data = {}
bot.broadcast_levels = {}
