"""Admin diagnostics command handlers."""
from __future__ import annotations

import logging

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.users import list_admin_ids
from services.diagnostics import diagnostics_text, perform_system_diagnostics

process_xlsx_report_file = None


logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    if user_id in PERMANENT_ADMINS or user_id in ADMIN_IDS:
        return True
    try:
        return user_id in list_admin_ids()
    except Exception as exc:
        logger.error("Could not check admin status for user %s: %s", user_id, exc)
        return False


def register_diagnostics_handlers(bot, context: dict | None = None) -> None:
    global process_xlsx_report_file
    if context and context.get("process_xlsx_report_file") is not None:
        process_xlsx_report_file = context["process_xlsx_report_file"]
    @bot.message_handler(commands=["healthcheck", "diag", "diagnostics"])
    def handle_system_healthcheck(message):
        if not _is_admin(message.from_user.id):
            bot.reply_to(message, "❌ Эта команда доступна только администраторам.")
            return

        diagnostics, overall_status = perform_system_diagnostics(bot)
        bot.reply_to(message, diagnostics_text(diagnostics, overall_status))


    @bot.message_handler(commands=["test_cover"])
    def test_cover_command(message):
        user_id = message.from_user.id
        user_data = getattr(bot, "user_data", {}).get(user_id, {})
        logger.info("DEBUG [test_cover_command] User %s data: %s", user_id, list(user_data.keys()))
        cover_file_id = user_data.get("cover_file_id")
        if cover_file_id:
            bot.send_message(
                message.chat.id,
                f"✅ Cover file ID найден: {cover_file_id}\n\nВсе ключи в user_data: {list(user_data.keys())}",
            )
        else:
            bot.send_message(
                message.chat.id,
                f"❌ Cover file ID не найден!\n\nВсе ключи в user_data: {list(user_data.keys())}",
            )


    @bot.message_handler(content_types=["photo", "document"])
    def handle_cover_test(message):
        """Simple photo/document diagnostic handler and XLSX report attachment bridge."""
        user_id = message.from_user.id
        if not hasattr(bot, "user_data"):
            bot.user_data = {}
        bot.user_data.setdefault(user_id, {})

        if (
            getattr(message, "document", None)
            and "attaching_xlsx_report" in bot.user_data[user_id]
            and process_xlsx_report_file is not None
        ):
            report_id = bot.user_data[user_id]["attaching_xlsx_report"]
            process_xlsx_report_file(message, report_id)
            return

        if getattr(message, "photo", None):
            file_id = message.photo[-1].file_id
            bot.user_data[user_id]["test_cover_file_id"] = file_id
            logger.info("Test: Saved photo cover for user %s: %s", user_id, file_id)
            bot.send_message(message.chat.id, f"✅ Тестовое фото сохранено: {file_id}")
        elif getattr(message, "document", None):
            file_id = message.document.file_id
            bot.user_data[user_id]["test_cover_file_id"] = file_id
            logger.info("Test: Saved document cover for user %s: %s", user_id, file_id)
            bot.send_message(message.chat.id, f"✅ Тестовый документ сохранен: {file_id}")
