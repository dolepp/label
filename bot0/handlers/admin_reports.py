"""Admin report request list handlers."""
from __future__ import annotations

import logging

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.admin_reports import count_report_statuses, list_admin_report_requests
from db.repositories.users import list_admin_ids


logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    if user_id in PERMANENT_ADMINS or user_id in ADMIN_IDS:
        return True
    try:
        return user_id in list_admin_ids()
    except Exception as exc:
        logger.error("Could not check admin status for user %s: %s", user_id, exc)
        return False


def _format_report_button(report: dict) -> str:
    status_emoji = {
        "pending": "⏳",
        "processing": "🔄",
        "completed": "✅",
        "rejected": "❌",
    }.get(report.get("status"), "❓")
    created_at = report.get("created_at")
    created_str = created_at.strftime("%d.%m.%Y %H:%M") if created_at else "дата не указана"
    user_name = report.get("user_name") or f"ID: {report.get('user_id')}"
    release_name = report.get("release_name") or "без релиза"
    return f"{status_emoji} {user_name} - {release_name} ({created_str})"


def _admin_reports_text(reports: list[dict]) -> str:
    counts = count_report_statuses(reports)
    return (
        f"📊 Запросы отчетов ({len(reports)})\n\n"
        "📋 Список всех запросов отчетов:\n"
        f"⏳ Ожидающие обработки: {counts['pending']}\n"
        f"🔄 В процессе: {counts['processing']}\n"
        f"✅ Завершенные: {counts['completed']}\n"
        f"❌ Отклоненные: {counts['rejected']}\n\n"
        "Выберите отчет для просмотра:"
    )


def _admin_reports_markup(reports: list[dict]):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for report in reports:
        markup.add(
            types.InlineKeyboardButton(
                _format_report_button(report),
                callback_data=f"admin_view_report_{report['id']}",
            )
        )
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_users"))
    return markup


def _empty_reports_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_users"))
    return markup


def register_admin_report_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "admin_report_requests")
    def handle_admin_report_requests(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут просматривать запросы отчетов", show_alert=True)
            return

        try:
            reports = list_admin_report_requests()
        except Exception as exc:
            logger.error("Error in admin report requests: %s", exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при получении запросов отчетов", show_alert=True)
            return

        if not reports:
            bot.edit_message_text(
                "📊 Запросы отчетов\n\n❌ Нет активных запросов отчетов",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=_empty_reports_markup(),
            )
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _admin_reports_text(reports),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_admin_reports_markup(reports),
        )

