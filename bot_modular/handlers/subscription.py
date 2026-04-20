# -*- coding: utf-8 -*-
"""Проверка подписки на канал и доступ бота к каналу."""
import logging
import time
from telebot import types

from core.bot import bot
from handlers.constants import CHANNEL_USERNAME

logger = logging.getLogger(__name__)

_subscription_cache = {}
_SUBSCRIPTION_CACHE_TTL = 300


def test_channel_access():
    """Тестирование доступа бота к каналу."""
    try:
        chat_info = bot.get_chat(CHANNEL_USERNAME)
        logger.info(f"✅ Channel access test successful: {chat_info.title}")
        bot_member = bot.get_chat_member(CHANNEL_USERNAME, bot.get_me().id)
        logger.info(f"✅ Bot member status: {bot_member.status}")
        if bot_member.status in ('administrator', 'creator'):
            logger.info("✅ Bot has admin rights in channel")
            return True
        logger.warning("⚠️ Bot is not an administrator in the channel")
        return False
    except Exception as e:
        logger.error(f"❌ Channel access test failed: {e}")
        return False


def check_channel_subscription(user_id, force_check=False):
    """Проверка подписки пользователя на канал (с кэшем 5 мин)."""
    now = time.time()
    if not force_check and user_id in _subscription_cache:
        is_subscribed, cached_at = _subscription_cache[user_id]
        if now - cached_at < _SUBSCRIPTION_CACHE_TTL:
            return is_subscribed
    try:
        chat_member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        is_subscribed = chat_member.status in ('member', 'administrator', 'creator')
        _subscription_cache[user_id] = (is_subscribed, now)
        return is_subscribed
    except Exception as e:
        logger.error(f"Error checking channel subscription for user {user_id}: {e}")
        if "chat not found" in str(e).lower() or "bot is not a member" in str(e).lower():
            logger.error("Bot is not added to the channel as administrator!")
        return False


def require_channel_subscription(func):
    """Декоратор для обязательной подписки на канал."""
    def wrapper(message):
        user_id = message.from_user.id
        if not check_channel_subscription(user_id):
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME[1:]}"))
            markup.add(types.InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription"))
            bot.reply_to(
                message,
                "🔔 Для использования бота необходимо подписаться на наш канал!\n\n"
                f"📢 Канал: {CHANNEL_USERNAME}\n"
                "🎵 После подписки нажмите кнопку 'Я подписался'",
                reply_markup=markup
            )
            return
        return func(message)
    return wrapper
