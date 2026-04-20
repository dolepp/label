"""Admin per-user report request list handlers."""
from __future__ import annotations

import logging

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.admin_user_reports import get_user_identity, list_user_report_requests_for_admin
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


def _display_name(user: dict) -> str:
    if user.get("name") and user.get("tg"):
        return f"{user['name']} (@{user['tg']})"
    return f"ID: {user['telegram_id']}"


def _report_status_emoji(status: str | None) -> str:
    return {
        "pending": "⏳",
        "processing": "🔄",
        "completed": "✅",
        "rejected": "❌",
    }.get(status, "❓")


def _user_reports_text(user: dict, reports: list[dict]) -> str:
    display_name = _display_name(user)
    if not reports:
        return f"📊 Запросы отчетов пользователя {display_name}\n\n❌ У пользователя нет запросов отчетов"

    lines = [f"📊 Запросы отчетов пользователя {display_name}", ""]
    for report in reports:
        created_at = report.get("created_at")
        date_str = created_at.strftime("%d.%m.%Y %H:%M") if created_at else "Не указана"
        lines.extend(
            [
                f"{_report_status_emoji(report.get('status'))} <b>{report.get('request_type')}</b> - {report.get('release_type')}",
                f"📅 {date_str}",
                f"📝 Статус: {report.get('status')}",
            ]
        )
        if report.get("notes"):
            lines.append(f"💬 {report['notes']}")
        lines.append("")
    return "\n".join(lines)


def _user_reports_markup(user_id: int, reports: list[dict]):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for report in reports:
        markup.add(
            types.InlineKeyboardButton(
                f"📋 {report.get('request_type')} - {report.get('release_type')} ({report.get('status')})",
                callback_data=f"view_report_{report['id']}",
            )
        )
    markup.add(types.InlineKeyboardButton("◀️ К списку пользователей", callback_data="admin_users"))
    markup.add(types.InlineKeyboardButton("◀️ В админ панель", callback_data="admin_back"))
    return markup


def register_admin_user_report_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data.startswith("user_reports_"))
    def handle_user_reports(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
            return

        try:
            user_id = int(call.data.split("_")[2])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return

        try:
            user = get_user_identity(user_id)
            reports = list_user_report_requests_for_admin(user_id) if user else []
        except Exception as exc:
            logger.error("Error showing user reports: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return

        if not user:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _user_reports_text(user, reports),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_user_reports_markup(user_id, reports),
        )

