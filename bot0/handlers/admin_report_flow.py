"""Report request and XLSX attachment flow migrated from the legacy monolith."""
from __future__ import annotations

from db.repositories.account_connections import notification_chat_id
from core.config import WEB_APP_URL

import logging
from datetime import datetime
from typing import Any, Callable

from telebot import types

from db.repositories.admin_reports import get_admin_report_request, mark_report_processing
from db.repositories.reports import (
    attach_xlsx_report_file,
    complete_report_with_existing_file,
    confirm_report_file_upload,
    create_release_report_request,
    get_release_for_report_request,
    get_user_report_detail,
    has_pending_release_report,
    list_report_admin_ids,
)
from handlers.admin_reports import _admin_report_detail_markup, _admin_report_detail_text, _is_admin as repo_is_admin

logger = logging.getLogger(__name__)

bot = None
is_admin: Callable[[int], bool] | None = None
has_access_level: Callable[[int, list[str]], bool] | None = None
get_all_admins: Callable[[], list[int]] | None = None


def configure_admin_report_flow(**context: Any) -> None:
    globals().update({key: value for key, value in context.items() if value is not None})


def _require(name: str) -> Any:
    value = globals().get(name)
    if value is None:
        raise RuntimeError(f"admin report flow dependency is not configured: {name}")
    return value


def _current_bot():
    return _require("bot")


def _is_admin_user(user_id: int) -> bool:
    checker = globals().get("is_admin")
    if checker is not None:
        try:
            return bool(checker(user_id))
        except Exception as exc:
            logger.error("Configured is_admin failed for user %s: %s", user_id, exc)
    access_checker = globals().get("has_access_level")
    if access_checker is not None:
        try:
            return bool(access_checker(user_id, ["admin"]))
        except Exception as exc:
            logger.error("Configured has_access_level failed for user %s: %s", user_id, exc)
    return repo_is_admin(user_id)


def _admin_ids() -> list[int]:
    provider = globals().get("get_all_admins")
    if provider is not None:
        try:
            return list(provider())
        except Exception as exc:
            logger.error("Configured get_all_admins failed: %s", exc)
    return list_report_admin_ids()


def _render_admin_report(call, report_id: int) -> None:
    current_bot = _current_bot()
    report = get_admin_report_request(report_id)
    if not report:
        current_bot.answer_callback_query(call.id, "❌ Запрос отчета не найден", show_alert=True)
        return
    current_bot.edit_message_text(
        _admin_report_detail_text(report),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=_admin_report_detail_markup(report),
    )


def _xlsx_cancel_markup(report_id: int):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data=f"admin_view_report_{report_id}"))
    return markup


def _report_status_emoji(status: str | None) -> str:
    return {
        "pending": "⏳",
        "processing": "🔄",
        "completed": "✅",
        "rejected": "❌",
    }.get(status, "❓")


def handle_report_request(call):
    """Handle release-specific report request from user."""
    current_bot = _current_bot()
    try:
        parts = call.data.split("_")
        if len(parts) < 4:
            current_bot.answer_callback_query(call.id, "❌ Неверный запрос отчета", show_alert=True)
            return
        report_type = parts[2]
        release_id = int(parts[3])

        release = get_release_for_report_request(release_id, call.from_user.id)
        if not release:
            current_bot.answer_callback_query(call.id, "❌ Релиз не найден", show_alert=True)
            return

        user_id = release["user_id"]
        pending_exists = has_pending_release_report(user_id, release_id)
        if pending_exists is None:
            current_bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
            return
        if pending_exists:
            current_bot.answer_callback_query(call.id, "❌ Запрос отчета уже существует", show_alert=True)
            return

        request_type = f"Отчет по {report_type}"
        report = create_release_report_request(user_id, release_id, release["release_type"], request_type)
        if not report:
            current_bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
            return

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
            types.InlineKeyboardButton("📊 Запросы отчетов", callback_data="admin_report_requests"),
        )
        for admin_id in _admin_ids():
            try:
                current_bot.send_message(
                    admin_id,
                    "📊 Новый запрос отчета!\n\n"
                    f"👤 Пользователь: @{call.from_user.username or 'без username'}\n"
                    f"🆔 Telegram ID: {user_id}\n"
                    f"📊 ID запроса: {report['id']}\n"
                    f"📀 Релиз: {release['release_name']}\n"
                    f"🎵 Тип: {release['release_type']}\n"
                    f"📋 Запрос: {request_type}\n\n"
                    "💡 Используйте кнопки ниже для быстрого доступа:",
                    reply_markup=markup,
                )
            except Exception as exc:
                logger.error("Failed to notify admin %s: %s", admin_id, exc)

        current_bot.answer_callback_query(call.id, "✅ Запрос отчета отправлен администраторам!", show_alert=True)
        done_markup = types.InlineKeyboardMarkup()
        done_markup.add(
            types.InlineKeyboardButton("📊 Запросить новый отчет", callback_data="request_new_report"),
            types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile"),
        )
        try:
            current_bot.edit_message_text(
                "✅ Запрос отчета отправлен администраторам!\n\nОжидайте уведомления о готовности отчета.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=done_markup,
            )
        except Exception:
            current_bot.send_message(
                call.message.chat.id,
                "✅ Запрос отчета отправлен администраторам!\n\nОжидайте уведомления о готовности отчета.",
                reply_markup=done_markup,
            )
    except Exception as exc:
        logger.error("Error in report request handler: %s", exc)
        current_bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)


def handle_start_report(call):
    current_bot = _current_bot()
    if not _is_admin_user(call.from_user.id):
        current_bot.answer_callback_query(call.id, "❌ Только администраторы могут управлять отчетами", show_alert=True)
        return
    try:
        report_id = int(call.data.split("_")[2])
        report = mark_report_processing(report_id, call.from_user.id)
    except Exception as exc:
        logger.error("Error starting report: %s", exc)
        current_bot.answer_callback_query(call.id, "❌ Ошибка при изменении статуса", show_alert=True)
        return
    if not report:
        current_bot.answer_callback_query(call.id, "❌ Отчет не найден", show_alert=True)
        return
    current_bot.answer_callback_query(call.id, "✅ Отчет взят в работу", show_alert=True)
    _render_admin_report(call, report_id)


def handle_attach_report(call):
    current_bot = _current_bot()
    if not _is_admin_user(call.from_user.id):
        current_bot.answer_callback_query(call.id, "❌ Только администраторы могут прикреплять отчеты", show_alert=True)
        return
    report_id = int(call.data.split("_")[2])
    call.data = f"attach_xlsx_report_{report_id}"
    handle_attach_xlsx_report(call)


def process_report_file(message, report_id):
    """Legacy manual report attachment entrypoint; reports are XLSX-only now."""
    current_bot = _current_bot()
    if not _is_admin_user(message.from_user.id):
        current_bot.reply_to(message, "❌ Только администраторы могут прикреплять отчеты")
        return
    current_bot.reply_to(
        message,
        "❌ Отчеты больше не прикрепляются вручную!\n\n"
        "📊 Для создания отчета используйте функцию '📎 Создать XLSX отчет' в админ панели.",
    )


def handle_complete_report(call):
    current_bot = _current_bot()
    if not _is_admin_user(call.from_user.id):
        current_bot.answer_callback_query(call.id, "❌ Только администраторы могут завершать отчеты", show_alert=True)
        return

    report_id = int(call.data.split("_")[2])
    try:
        result = complete_report_with_existing_file(report_id, call.from_user.id)
        if result["status"] == "connection_error":
            current_bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
            return
        if result["status"] == "not_found":
            current_bot.answer_callback_query(call.id, "❌ Отчет не найден", show_alert=True)
            return
        if result["status"] == "missing_file":
            current_bot.answer_callback_query(call.id, "❌ Сначала прикрепите файл отчета", show_alert=True)
            return

        user_id = result["user_id"]
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📊 Мои отчеты", **({"url": WEB_APP_URL + "/#profile"} if user_id < 0 else {"callback_data": "my_reports"})))
            current_bot.send_message(
                notification_chat_id(user_id),
                f"✅ Ваш отчет готов!\n\n"
                f"📊 Отчет #{report_id} был завершен администратором.\n"
                f"📎 Файл отчета прикреплен\n\n"
                f"Просмотрите отчет в разделе 'Мои отчеты'",
                reply_markup=markup,
            )
        except Exception as exc:
            logger.error("Failed to notify user %s: %s", user_id, exc)
        current_bot.answer_callback_query(call.id, "✅ Отчет завершен", show_alert=True)
        _render_admin_report(call, report_id)
    except Exception as exc:
        logger.error("Error completing report %s: %s", report_id, exc)
        current_bot.answer_callback_query(call.id, "❌ Ошибка при завершении отчета", show_alert=True)


def handle_view_report(call):
    current_bot = _current_bot()
    report_id = int(call.data.split("_")[2])
    if _is_admin_user(call.from_user.id):
        _render_admin_report(call, report_id)
        return

    try:
        report = get_user_report_detail(report_id, call.from_user.id)
        if not report:
            current_bot.answer_callback_query(call.id, "❌ Запрос отчета не найден", show_alert=True)
            return
        display_name = (
            f"{report['user_name']} (@{report['username']})"
            if report.get("user_name") and report.get("username")
            else f"ID: {report['user_id']}"
        )
        created_at = report.get("created_at")
        report_text = (
            f"📊 Запрос отчета #{report_id}\n\n"
            f"👤 Пользователь: {display_name}\n"
            f"🎵 Релиз: {report.get('release_name') or 'Не указан'}\n"
            f"📀 Тип: {report.get('release_type')}\n"
            f"📋 Запрос: {report.get('request_type')}\n"
            f"{_report_status_emoji(report.get('status'))} Статус: {report.get('status')}\n"
            f"📅 Создан: {created_at.strftime('%d.%m.%Y %H:%M') if created_at else 'Не указана'}\n"
        )
        if report.get("notes"):
            report_text += f"💬 Заметки: {report['notes']}\n"
        if report.get("report_file_id"):
            report_text += "📎 Отчет прикреплен\n"

        markup = types.InlineKeyboardMarkup(row_width=2)
        if report.get("status") == "completed" and report.get("report_file_id"):
            markup.add(types.InlineKeyboardButton("📎 Скачать отчет", callback_data=f"download_report_{report_id}"))
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="my_reports"))
        current_bot.edit_message_text(
            report_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
    except Exception as exc:
        logger.error("Error viewing report: %s", exc)
        current_bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)


def handle_attach_xlsx_report(call):
    current_bot = _current_bot()
    if not _is_admin_user(call.from_user.id):
        current_bot.answer_callback_query(call.id, "❌ Только администраторы могут прикреплять отчеты", show_alert=True)
        return
    report_id = int(call.data.split("_")[3])
    if not hasattr(current_bot, "user_data"):
        current_bot.user_data = {}
    current_bot.user_data[call.from_user.id] = {"attaching_xlsx_report": report_id}
    current_bot.edit_message_text(
        f"📎 Прикрепление XLSX отчета #{report_id}\n\n"
        f"📊 Отправьте готовый файл отчета в формате .xlsx\n\n"
        f"⚠️ Требования к файлу:\n"
        f"• Формат: .xlsx (Excel)\n"
        f"• Размер: до 50MB\n"
        f"• Содержание: детальная информация о пользователе\n\n"
        f"Отправьте XLSX файл в следующем сообщении.",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=_xlsx_cancel_markup(report_id),
    )
    current_bot.register_next_step_handler(call.message, process_xlsx_report_file, report_id)


def process_xlsx_report_file(message, report_id):
    current_bot = _current_bot()
    if not _is_admin_user(message.from_user.id):
        current_bot.reply_to(message, "❌ Только администраторы могут прикреплять отчеты")
        return
    if not getattr(message, "document", None):
        current_bot.reply_to(message, "❌ Пожалуйста, отправьте файл", reply_markup=_xlsx_cancel_markup(report_id))
        return
    file_name = (message.document.file_name or "").lower()
    if not file_name.endswith(".xlsx"):
        current_bot.reply_to(message, "❌ Файл должен быть в формате .xlsx (Excel)", reply_markup=_xlsx_cancel_markup(report_id))
        return
    file_size = getattr(message.document, "file_size", 0) or 0
    if file_size > 50 * 1024 * 1024:
        current_bot.reply_to(message, "❌ Файл слишком большой. Максимум 50MB", reply_markup=_xlsx_cancel_markup(report_id))
        return

    try:
        report_info = attach_xlsx_report_file(report_id, message.document.file_id, message.from_user.id)
        if not report_info:
            current_bot.reply_to(message, "❌ Отчет не найден")
            return
        user_id = report_info["user_id"]
        request_type = report_info["request_type"]
        user_name = report_info["user_name"]
        username = report_info.get("username")
        try:
            current_bot.send_document(
                notification_chat_id(user_id),
                message.document.file_id,
                caption=f"📊 Ваш отчет #{report_id} готов!\n\n"
                        f"📋 Тип запроса: {request_type}\n"
                        f"👤 Подготовлен администратором\n"
                        f"📅 Дата: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                        f"📎 Отчет содержит детальную информацию в формате Excel.\n"
                        f"💾 Файл сохранен в формате XLSX для удобного просмотра и анализа.",
                visible_file_name=f"Отчет_{user_name}_{datetime.now().strftime('%d%m%Y')}.xlsx",
            )
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("◀️ Назад к отчетам", callback_data="admin_report_requests"))
            current_bot.reply_to(
                message,
                f"✅ XLSX отчет #{report_id} успешно отправлен пользователю {user_name} (@{username or 'без username'})\n\n"
                f"📊 Тип отчета: {request_type}\n"
                f"📅 Дата отправки: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"📎 Отчет отправлен в формате XLSX",
                reply_markup=markup,
            )
        except Exception as exc:
            logger.error("Error sending report to user: %s", exc)
            current_bot.reply_to(message, f"❌ Ошибка отправки отчета: {exc}")
    except Exception as exc:
        logger.error("Error processing XLSX report file: %s", exc)
        current_bot.reply_to(message, f"❌ Ошибка: {exc}")
    finally:
        user_data = getattr(current_bot, "user_data", {})
        if message.from_user.id in user_data:
            user_data[message.from_user.id].pop("attaching_xlsx_report", None)


def process_report_file_upload(message, report_id):
    """Legacy confirmation-based upload flow; kept for compatibility."""
    current_bot = _current_bot()
    process_xlsx_report_file(message, report_id)
    if not getattr(message, "document", None):
        return
    user_id = message.from_user.id
    file_size = getattr(message.document, "file_size", 0) or 0
    file_name = message.document.file_name or "report_file"
    if file_size > 10 * 1024 * 1024:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data=f"view_report_{report_id}"))
        current_bot.reply_to(message, "❌ Файл слишком большой. Максимум 10MB", reply_markup=markup)
        return
    if not hasattr(current_bot, "user_data"):
        current_bot.user_data = {}
    current_bot.user_data.setdefault(user_id, {})["report_file_info"] = {
        "report_id": report_id,
        "file_id": message.document.file_id,
        "file_name": file_name,
        "file_size": file_size,
    }
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirm_report_upload_{report_id}"),
        types.InlineKeyboardButton("❌ Отмена", callback_data=f"view_report_{report_id}"),
    )
    current_bot.reply_to(
        message,
        f"📎 Подтвердите прикрепление файла:\n\n"
        f"📄 Файл: {file_name}\n"
        f"📏 Размер: {file_size / 1024:.1f} KB\n"
        f"🔖 ID файла: {message.document.file_id}",
        reply_markup=markup,
    )


def handle_confirm_report_upload(call):
    current_bot = _current_bot()
    report_id = int(call.data.split("_")[3])
    user_id = call.from_user.id
    if not _is_admin_user(user_id):
        current_bot.answer_callback_query(call.id, "❌ Только администраторы могут прикреплять отчеты", show_alert=True)
        return
    user_data = getattr(current_bot, "user_data", {})
    file_info = user_data.get(user_id, {}).get("report_file_info")
    if not file_info or file_info["report_id"] != report_id:
        current_bot.answer_callback_query(call.id, "❌ Информация о файле не найдена", show_alert=True)
        return

    try:
        report_info = confirm_report_file_upload(report_id, file_info["file_id"], user_id)
        if not report_info:
            current_bot.answer_callback_query(call.id, "❌ Отчет не найден", show_alert=True)
            return
        try:
            current_bot.send_message(
                notification_chat_id(report_info["user_id"]),
                f"✅ Ваш отчет готов!\n\n"
                f"📊 Запрос: {report_info['request_type']}\n"
                f"🎵 Тип: {report_info['release_type']}\n"
                f"📎 Файл отчета прикреплен администратором",
            )
        except Exception as exc:
            logger.error("Failed to notify user %s: %s", report_info["user_id"], exc)
        user_data.get(user_id, {}).pop("report_file_info", None)
        current_bot.answer_callback_query(call.id, "✅ Отчет успешно прикреплен!", show_alert=True)
        _render_admin_report(call, report_id)
    except Exception as exc:
        logger.error("Error updating report with file: %s", exc)
        current_bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)


def register_admin_report_flow_handlers(bot, context: dict | None = None) -> None:
    configure_admin_report_flow(bot=bot, **(context or {}))

    @bot.callback_query_handler(func=lambda call: (getattr(call, "data", "") or "").startswith("request_report_"))
    def report_request_callback(call):
        handle_report_request(call)

    @bot.callback_query_handler(func=lambda call: (getattr(call, "data", "") or "").startswith("start_report_"))
    def start_report_callback(call):
        handle_start_report(call)

    @bot.callback_query_handler(func=lambda call: (getattr(call, "data", "") or "").startswith("attach_report_"))
    def attach_report_callback(call):
        handle_attach_report(call)

    @bot.callback_query_handler(func=lambda call: (getattr(call, "data", "") or "").startswith("complete_report_"))
    def complete_report_callback(call):
        handle_complete_report(call)

    @bot.callback_query_handler(func=lambda call: (getattr(call, "data", "") or "").startswith("view_report_"))
    def view_report_callback(call):
        handle_view_report(call)

    @bot.callback_query_handler(func=lambda call: (getattr(call, "data", "") or "").startswith("attach_xlsx_report_"))
    def attach_xlsx_report_callback(call):
        handle_attach_xlsx_report(call)

    @bot.callback_query_handler(func=lambda call: (getattr(call, "data", "") or "").startswith("confirm_report_upload_"))
    def confirm_report_upload_callback(call):
        handle_confirm_report_upload(call)
