"""Per-user in-memory storage helpers detached from label.py."""
from __future__ import annotations

bot = None


def configure(bot_instance) -> None:
    global bot
    bot = bot_instance


def ensure_user_storage(user_id):
    if bot is None:
        raise RuntimeError("user storage bot is not configured")
    if not hasattr(bot, "user_data"):
        bot.user_data = {}
    return bot.user_data.setdefault(user_id, {})
