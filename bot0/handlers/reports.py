"""Report request handlers for the modular bot."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from telebot import types

from db.repositories.reports import (
    cancel_pending_report,
    count_user_releases,
    create_general_report_request,
    format_report_datetime,
    get_active_general_report,
    get_latest_user_report,
    get_user_identity,
    get_user_report,
    list_report_admin_ids,
    list_user_reports,
)


logger = logging.getLogger(__name__)

STATUS_INFO = {
    "pending": ("⏳", "В обработке"),
    "processing": ("🔄", "Готовится"),
    "completed": ("✅", "Готов"),
    "rejected": ("❌", "Отклонен"),
}


def _back_to_profile_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile"))
    return markup


def _reports_markup(reports: list[dict[str, Any]]):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if reports:
        latest = reports[0]
        emoji = STATUS_INFO.get(latest["status"], ("❓", "Неизвестно"))[0]
        created = format_report_datetime(latest["created_at"])
        markup.add(types.InlineKeyboardButton(f"📊 Посмотреть последний отчет ({emoji} {created})", callback_data="view_latest_report"))
        if latest["status"] == "pending":
            markup.add(types.InlineKeyboardButton("❌ Отменить запрос отчета", callback_data=f"cancel_report_{latest['id']}"))
    markup.add(
        types.InlineKeyboardButton("📊 Запросить новый отчет", callback_data="request_new_report"),
        types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile"),
    )
    return markup


def _report_text(report: dict[str, Any]) -> str:
    emoji, status_text = STATUS_INFO.get(report["status"], ("❓", "Неизвестно"))
    lines = [
        f"📊 Отчет #{report['id']}",
        "",
        f"📋 Тип отчета: {report['request_type']}",
        f"📅 Дата запроса: {format_report_datetime(report['created_at'])}",
        f"📊 Статус: {emoji} {status_text}",
    ]
    if report["completed_at"]:
        lines.append(f"✅ Дата завершения: {format_report_datetime(report['completed_at'])}")
    if report["notes"]:
        lines.extend(["", f"💬 Комментарий: {report['notes']}"])
    if report["status"] == "rejected" and not report["notes"]:
        lines.extend(["", "❌ Отчет был отклонен. Обратитесь к администратору для уточнения деталей."])
    return "\n".join(lines)


def _report_detail_markup(report: dict[str, Any]):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if report["status"] == "completed" and report["report_file_id"]:
        markup.add(types.InlineKeyboardButton("📎 Скачать отчет (Excel)", callback_data=f"download_report_{report['id']}"))
    if report["status"] == "pending":
        markup.add(types.InlineKeyboardButton("❌ Отменить запрос", callback_data=f"cancel_report_{report['id']}"))
    markup.add(types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile"))
    return markup


def _send_reports(bot, chat_id: int, user_id: int) -> None:
    reports = list_user_reports(user_id)
    if not reports:
        bot.send_message(
            chat_id,
            "📊 У вас пока нет запросов отчетов\n\n"
            "💡 Вы можете запросить общий отчет по всем вашим релизам в формате Excel",
            reply_markup=_reports_markup([]),
        )
        return

    lines = ["📊 Ваши отчеты:\n"]
    for report in reports[:5]:
        emoji, status_text = STATUS_INFO.get(report["status"], ("❓", "Неизвестно"))
        lines.append(
            f"• #{report['id']} {report['request_type']} | {emoji} {status_text} | "
            f"{format_report_datetime(report['created_at'])}"
        )
    bot.send_message(chat_id, "\n".join(lines), reply_markup=_reports_markup(reports))


def _notify_admins(bot, report: dict[str, Any], user: dict[str, Any]) -> None:
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
        types.InlineKeyboardButton("📊 Запросы отчетов", callback_data="admin_report_requests"),
    )
    username = user.get("username") or "нет username"
    text = (
        "📊 Новый запрос отчета!\n\n"
        f"👤 Пользователь: {user.get('name') or 'Неизвестный пользователь'} (@{username})\n"
        f"🆔 Telegram ID: {report['user_id']}\n"
        f"📊 ID запроса: {report['id']}\n"
        f"📋 Тип: {report['request_type']}\n\n"
        "💡 Перейдите в админ панель -> Пользователи -> Запросы отчетов для ответа"
    )
    for admin_id in list_report_admin_ids():
        try:
            bot.send_message(admin_id, text, reply_markup=markup)
        except Exception as exc:
            logger.error("Failed to notify admin %s about report request %s: %s", admin_id, report["id"], exc)


def register_report_handlers(bot) -> None:
    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "📊 Мои отчеты")
    def handle_my_reports(message):
        _send_reports(bot, message.chat.id, message.from_user.id)

    @bot.callback_query_handler(func=lambda call: call.data == "my_reports")
    def handle_my_reports_callback(call):
        bot.answer_callback_query(call.id)
        _send_reports(bot, call.message.chat.id, call.from_user.id)

    @bot.callback_query_handler(func=lambda call: call.data == "request_new_report")
    def handle_request_new_report(call):
        user_id = call.from_user.id
        releases_count = count_user_releases(user_id)
        if releases_count is None:
            bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
            return
        if releases_count == 0:
            bot.edit_message_text(
                "❌ У вас нет релизов для запроса отчета\n\nСначала создайте релиз, а затем запросите отчет.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=_back_to_profile_markup(),
            )
            return

        active_report = get_active_general_report(user_id)
        if active_report:
            bot.edit_message_text(
                "⏳ У вас уже есть активный запрос отчета\n\nДождитесь его выполнения или отмените текущий запрос.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=_back_to_profile_markup(),
            )
            return

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_report_request"),
            types.InlineKeyboardButton("❌ Отмена", callback_data="back_to_profile"),
        )
        bot.edit_message_text(
            "📊 Запрос отчета\n\n"
            f"Вы запрашиваете общий отчет по всем вашим релизам ({releases_count} релиз(ов))\n\n"
            "Отчет будет включать:\n"
            "• Статистику по всем релизам\n"
            "• Общую аналитику\n"
            "• Финансовые показатели\n"
            "• Красивое оформление в формате Excel\n\n"
            "Подтвердите запрос?",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )

    @bot.callback_query_handler(func=lambda call: call.data == "confirm_report_request")
    def handle_confirm_report_request(call):
        user_id = call.from_user.id
        if get_active_general_report(user_id):
            bot.answer_callback_query(call.id, "⏳ У вас уже есть активный запрос отчета", show_alert=True)
            return
        try:
            report = create_general_report_request(user_id)
        except Exception as exc:
            logger.error("Could not create report request for user %s: %s", user_id, exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при создании запроса отчета", show_alert=True)
            return

        if report is None:
            bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
            return

        bot.edit_message_text(
            "✅ Запрос отчета успешно отправлен!\n\n"
            "📊 Ваш запрос на получение общего отчета по всем релизам принят в обработку.\n"
            "📊 Отчет будет сгенерирован в формате Excel (.xlsx)\n"
            "⏳ Обычно отчет готовится в течение 1-3 рабочих дней.\n\n"
            "Вы получите уведомление, когда отчет будет готов.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_back_to_profile_markup(),
        )
        _notify_admins(bot, report, get_user_identity(user_id))

    @bot.callback_query_handler(func=lambda call: call.data.startswith("cancel_report_"))
    def handle_cancel_report(call):
        try:
            report_id = int(call.data.split("_")[2])
        except ValueError:
            bot.answer_callback_query(call.id, "❌ Неверный ID отчета", show_alert=True)
            return
        try:
            report = cancel_pending_report(report_id, call.from_user.id)
        except Exception as exc:
            logger.error("Could not cancel report %s for user %s: %s", report_id, call.from_user.id, exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при отмене отчета", show_alert=True)
            return
        if report is None:
            bot.answer_callback_query(call.id, "❌ Отчет не найден или уже не ожидает обработки", show_alert=True)
            return

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📊 Мои отчеты", callback_data="my_reports"))
        bot.edit_message_text(
            f"✅ Запрос отчета #{report_id} отменен.\n\n"
            f"📋 Тип отчета: {report['request_type']}\n"
            f"📅 Дата отмены: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
            "💡 Вы можете запросить новый отчет в любое время.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )

    @bot.callback_query_handler(func=lambda call: call.data == "view_latest_report")
    def handle_view_latest_report(call):
        report = get_latest_user_report(call.from_user.id)
        if report is None:
            bot.answer_callback_query(call.id, "❌ Отчет не найден", show_alert=True)
            return
        bot.edit_message_text(
            _report_text(report),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_report_detail_markup(report),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("download_report_"))
    def handle_download_report(call):
        try:
            report_id = int(call.data.split("_")[2])
        except ValueError:
            bot.answer_callback_query(call.id, "❌ Неверный ID отчета", show_alert=True)
            return

        report = get_user_report(report_id, call.from_user.id)
        if report is None:
            bot.answer_callback_query(call.id, "❌ Отчет не найден", show_alert=True)
            return
        if report["status"] != "completed":
            bot.answer_callback_query(call.id, "❌ Отчет еще не готов", show_alert=True)
            return
        if not report["report_file_id"]:
            bot.answer_callback_query(call.id, "❌ Файл отчета не найден", show_alert=True)
            return

        try:
            bot.send_document(
                call.message.chat.id,
                report["report_file_id"],
                caption=(
                    f"📊 Отчет #{report_id}\n\n"
                    "✅ Ваш отчет готов к использованию!\n"
                    f"📅 Дата скачивания: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                    "💡 Если у вас есть вопросы по отчету, обратитесь к администратору."
                ),
            )
            bot.answer_callback_query(call.id, "✅ Отчет отправлен!")
        except Exception as exc:
            logger.error("Error sending report file %s: %s", report_id, exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при отправке файла", show_alert=True)
