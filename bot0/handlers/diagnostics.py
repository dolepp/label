"""Admin diagnostics command handlers."""
from __future__ import annotations

import logging

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.users import list_admin_ids
from services.diagnostics import diagnostics_text, perform_system_diagnostics


logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    if user_id in PERMANENT_ADMINS or user_id in ADMIN_IDS:
        return True
    try:
        return user_id in list_admin_ids()
    except Exception as exc:
        logger.error("Could not check admin status for user %s: %s", user_id, exc)
        return False


def register_diagnostics_handlers(bot) -> None:
    @bot.message_handler(commands=["healthcheck", "diag", "diagnostics"])
    def handle_system_healthcheck(message):
        if not _is_admin(message.from_user.id):
            bot.reply_to(message, "❌ Эта команда доступна только администраторам.")
            return

        diagnostics, overall_status = perform_system_diagnostics(bot)
        bot.reply_to(message, diagnostics_text(diagnostics, overall_status))
