"""Admin report request list handlers."""
from __future__ import annotations

from db.repositories.account_connections import notification_chat_id

import logging

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.admin_reports import (
    count_report_statuses,
    get_admin_report_request,
    list_admin_report_requests,
    list_pending_report_requests,
    mark_report_processing,
    reject_report_request,
)
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


def _admin_report_detail_text(report: dict) -> str:
    status_emoji = {
        "pending": "⏳",
        "processing": "🔄",
        "completed": "✅",
        "rejected": "❌",
    }.get(report.get("status"), "❓")
    username = report.get("username") or "без username"
    user_name = report.get("user_name") or f"ID: {report.get('user_id')}"
    created = report.get("created_at")
    created_str = created.strftime("%d.%m.%Y %H:%M") if created else "Не указана"
    text = (
        f"📊 Запрос отчета #{report['id']}\n\n"
        f"👤 Пользователь: {user_name} (@{username})\n"
        f"🎵 Релиз: {report.get('release_name') or 'Не указан'}\n"
        f"📀 Тип: {report.get('release_type') or 'GENERAL'}\n"
        f"📋 Запрос: {report.get('request_type') or 'Общий отчет'}\n"
        f"{status_emoji} Статус: {report.get('status')}\n"
        f"📅 Создан: {created_str}\n"
    )
    if report.get("notes"):
        text += f"💬 Заметки: {report['notes']}\n"
    if report.get("report_file_id"):
        text += "📎 Отчет прикреплен\n"
    return text


def _admin_report_detail_markup(report: dict):
    report_id = report["id"]
    markup = types.InlineKeyboardMarkup(row_width=2)
    if report.get("status") == "pending":
        markup.add(
            types.InlineKeyboardButton("✅ Принять", callback_data=f"accept_report_{report_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_report_{report_id}"),
        )
    if report.get("status") in {"pending", "processing"}:
        markup.add(types.InlineKeyboardButton("📎 Прикрепить XLSX отчет", callback_data=f"attach_xlsx_report_{report_id}"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data=f"user_reports_{report['user_id']}"))
    return markup


def _pending_report_text(report: dict, remaining: int) -> str:
    created = report.get("created_at")
    created_str = created.strftime("%d.%m.%Y %H:%M") if created else "дата не указана"
    username = report.get("username") or "без username"
    return (
        f"📊 Обработка отчета #{report['id']}\n\n"
        f"👤 Пользователь: {report.get('user_name') or report.get('user_id')} (@{username})\n"
        f"📅 Дата запроса: {created_str}\n"
        f"📋 Тип запроса: {report.get('request_type') or 'Общий отчет'}\n\n"
        "📊 Отчет будет создан в формате XLSX с детальной информацией\n"
        f"💡 Ожидают обработки: {remaining}"
    )


def _pending_report_markup(report_id: int, remaining: int):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Принять в работу", callback_data=f"admin_start_report_{report_id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"admin_reject_report_{report_id}"),
    )
    if remaining > 1:
        markup.add(types.InlineKeyboardButton(f"⏭️ Следующий ({remaining - 1} осталось)", callback_data="admin_process_pending_reports"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_report_requests"))
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



    def handle_admin_report_rejection_reason(message):
        admin_id = message.from_user.id
        state = getattr(bot, "user_data", {}).get(admin_id, {})
        report_id = state.get("report_id")
        if not report_id:
            bot.reply_to(message, "❌ Ошибка: неверный контекст. Вернитесь в админ панель.")
            return
        reason = (message.text or "").strip()
        if not reason:
            bot.reply_to(message, "❌ Пожалуйста, укажите причину отклонения")
            return
        try:
            report = reject_report_request(int(report_id), reason)
        except Exception as exc:
            logger.error("Error rejecting report %s: %s", report_id, exc)
            bot.reply_to(message, f"❌ Ошибка при отклонении отчета: {exc}")
            return
        if not report:
            bot.reply_to(message, "❌ Отчет не найден")
            return
        try:
            bot.send_message(
                notification_chat_id(report["user_id"]),
                f"❌ Ваш запрос отчета #{report_id} отклонен\n\n"
                f"📝 Причина: {reason}\n\n"
                "💡 Если вы считаете, что это ошибка, обратитесь к администратору.\n"
                "🔄 Вы можете создать новый запрос отчета в разделе 'Мой профиль' → 'Мои отчеты'.",
            )
        except Exception as exc:
            logger.error("Failed to notify user %s about report rejection: %s", report.get("user_id"), exc)
        getattr(bot, "user_data", {}).pop(admin_id, None)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад к отчетам", callback_data="admin_report_requests"))
        bot.reply_to(
            message,
            f"❌ Отчет #{report_id} отклонен!\n\n"
            "📊 Статус изменен на 'Отклонен'\n"
            "👤 Пользователь уведомлен\n"
            f"📝 Причина: {reason}",
            reply_markup=markup,
        )

    @bot.callback_query_handler(func=lambda call: call.data == "admin_process_pending_reports")
    def handle_admin_process_pending_reports(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут обрабатывать отчеты", show_alert=True)
            return
        try:
            pending_reports = list_pending_report_requests()
        except Exception as exc:
            logger.error("Error in handle_admin_process_pending_reports: %s", exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при получении ожидающих отчетов", show_alert=True)
            return
        if not pending_reports:
            bot.answer_callback_query(call.id, "✅ Нет ожидающих отчетов", show_alert=True)
            return
        report = pending_reports[0]
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _pending_report_text(report, len(pending_reports)),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_pending_report_markup(report["id"], len(pending_reports)),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_start_report_"))
    def handle_admin_start_report(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут обрабатывать отчеты", show_alert=True)
            return
        try:
            report_id = int(call.data.split("_")[3])
            report = mark_report_processing(report_id, call.from_user.id)
        except Exception as exc:
            logger.error("Error starting report: %s", exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при изменении статуса отчета", show_alert=True)
            return
        if not report:
            bot.answer_callback_query(call.id, "❌ Отчет не найден", show_alert=True)
            return
        try:
            bot.send_message(
                notification_chat_id(report["user_id"]),
                f"📊 Ваш запрос отчета #{report_id} принят в работу!\n\n"
                "🔄 Администратор начал подготовку отчета.\n"
                "⏳ Обычно отчет готовится в течение 1-3 рабочих дней.\n\n"
                "📊 Отчет будет подготовлен в формате XLSX с детальной информацией.\n"
                "Вы получите уведомление, когда отчет будет готов.",
            )
        except Exception as exc:
            logger.error("Failed to notify user %s about report start: %s", report.get("user_id"), exc)
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("📎 Создать XLSX отчет", callback_data=f"admin_send_report_{report_id}"),
            types.InlineKeyboardButton("◀️ Назад к отчетам", callback_data="admin_report_requests"),
        )
        bot.edit_message_text(
            f"✅ Отчет #{report_id} принят в работу!\n\n"
            "📊 Статус изменен на 'В обработке'\n"
            "👤 Пользователь уведомлен\n\n"
            "💡 Теперь можно подготовить XLSX отчет и отправить его пользователю.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_reject_report_"))
    def handle_admin_reject_report(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут отклонять отчеты", show_alert=True)
            return
        try:
            report_id = int(call.data.split("_")[3])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Неверный ID отчета", show_alert=True)
            return
        if not hasattr(bot, "user_data"):
            bot.user_data = {}
        bot.user_data[call.from_user.id] = {"report_id": report_id, "action": "reject_report"}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="admin_report_requests"))
        bot.edit_message_text(
            f"❌ Отклонение отчета #{report_id}\n\n"
            "📝 Укажите причину отклонения:\n\n"
            "💡 Примеры причин:\n"
            "• Недостаточно данных для составления отчета\n"
            "• Нарушение правил использования сервиса\n"
            "• Технические проблемы",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
        bot.register_next_step_handler(call.message, handle_admin_report_rejection_reason)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_view_report_"))
    def handle_admin_view_report(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут просматривать отчеты", show_alert=True)
            return
        try:
            report_id = int(call.data.split("_")[3])
            report = get_admin_report_request(report_id)
        except Exception as exc:
            logger.error("Error viewing admin report: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return
        if not report:
            bot.answer_callback_query(call.id, "❌ Запрос отчета не найден", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _admin_report_detail_text(report),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_admin_report_detail_markup(report),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("accept_report_"))
    def handle_accept_report(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут принимать отчеты", show_alert=True)
            return
        try:
            report_id = int(call.data.split("_")[2])
            report = mark_report_processing(report_id, call.from_user.id)
        except Exception as exc:
            logger.error("Error accepting report: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return
        if not report:
            bot.answer_callback_query(call.id, "❌ Отчет не найден", show_alert=True)
            return
        bot.answer_callback_query(call.id, "✅ Запрос принят в обработку!", show_alert=True)
        bot.edit_message_text(
            _admin_report_detail_text(report),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_admin_report_detail_markup(report),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("reject_report_"))
    def handle_reject_report(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут отклонять отчеты", show_alert=True)
            return
        try:
            report_id = int(call.data.split("_")[2])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Неверный ID отчета", show_alert=True)
            return
        if not hasattr(bot, "user_data"):
            bot.user_data = {}
        bot.user_data[call.from_user.id] = {"report_id": report_id, "action": "reject_report"}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data=f"admin_view_report_{report_id}"))
        bot.edit_message_text(
            f"❌ Отклонение отчета #{report_id}\n\n📝 Укажите причину отклонения:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
        bot.register_next_step_handler(call.message, handle_admin_report_rejection_reason)
