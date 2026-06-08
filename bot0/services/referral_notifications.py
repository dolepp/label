"""Referral notification helpers detached from label.py."""
from __future__ import annotations

import logging

from db.repositories.referrals import get_referrer_id_by_code

logger = logging.getLogger(__name__)
bot = None


def configure(bot_instance) -> None:
    global bot
    bot = bot_instance


def notify_referrer_about_visit(referral_code, visitor_id, visitor_username):
    if bot is None:
        return
    try:
        referrer_id = get_referrer_id_by_code(referral_code)
        if not referrer_id or referrer_id == visitor_id:
            return
        username_str = f"@{visitor_username}" if visitor_username else f"ID:{visitor_id}"
        bot.send_message(referrer_id, f"🔗 По вашей реферальной ссылке в бота зашёл пользователь {username_str}.")
    except Exception as exc:
        logger.error("Error in notify_referrer_about_visit: %s", exc)
