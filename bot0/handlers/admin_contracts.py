"""Admin contract list and detail handlers."""
from __future__ import annotations

import logging

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.admin_contracts import (
    attach_contract_file,
    complete_contract,
    count_contract_statuses,
    get_admin_contract,
    list_admin_contracts,
    update_contract_status,
    user_owns_contract,
)
from db.repositories.users import list_admin_ids
from db.repositories.contracts import get_user_contract


logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    if user_id in PERMANENT_ADMINS or user_id in ADMIN_IDS:
        return True
    try:
        return user_id in list_admin_ids()
    except Exception as exc:
        logger.error("Could not check admin status for user %s: %s", user_id, exc)
        return False


def _status_emoji(status: str | None) -> str:
    return {
        "pending": "⏳",
        "processing": "🔄",
        "completed": "✅",
        "rejected": "❌",
    }.get(status, "❓")


def _format_contract_button(contract: dict) -> str:
    created_at = contract.get("created_at")
    created_str = created_at.strftime("%d.%m.%Y %H:%M") if created_at else "дата не указана"
    user_name = contract.get("user_name") or f"ID: {contract.get('user_id')}"
    number = contract.get("contract_number") or f"#{contract.get('id')}"
    return f"{_status_emoji(contract.get('status'))} {user_name} - {number} ({created_str})"


def _admin_contracts_text(contracts: list[dict]) -> str:
    counts = count_contract_statuses(contracts)
    return (
        f"📋 Управление договорами ({len(contracts)})\n\n"
        "📋 Список всех договоров:\n"
        f"⏳ Ожидающие обработки: {counts['pending']}\n"
        f"🔄 В процессе: {counts['processing']}\n"
        f"✅ Завершенные: {counts['completed']}\n"
        f"❌ Отклоненные: {counts['rejected']}\n\n"
        "Выберите договор для просмотра:"
    )


def _admin_contract_detail_text(contract: dict) -> str:
    created_at = contract.get("created_at")
    completed_at = contract.get("completed_at")
    created_str = created_at.strftime("%d.%m.%Y %H:%M") if created_at else "дата не указана"
    completed_str = completed_at.strftime("%d.%m.%Y %H:%M") if completed_at else "не завершен"
    user_name = contract.get("user_name") or f"ID: {contract.get('user_id')}"
    username = contract.get("username") or "без username"
    file_text = "Прикреплен" if contract.get("contract_file_id") else "Не прикреплен"
    return (
        f"📋 Детали договора #{contract['id']}\n\n"
        f"👤 Пользователь: {user_name} (@{username})\n"
        f"📄 Номер: {contract.get('contract_number')}\n"
        f"📋 Тип: {contract.get('contract_type')}\n"
        f"📅 Создан: {created_str}\n"
        f"✅ Завершен: {completed_str}\n"
        f"🔄 Статус: {_status_emoji(contract.get('status'))} {contract.get('status')}\n"
        f"📎 Файл договора: {file_text}\n"
    )


def _admin_contracts_markup(contracts: list[dict]):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for contract in contracts:
        markup.add(
            types.InlineKeyboardButton(
                _format_contract_button(contract),
                callback_data=f"admin_view_contract_{contract['id']}",
            )
        )
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_users"))
    return markup


def _admin_contract_detail_markup(contract: dict):
    contract_id = contract["id"]
    status = contract.get("status")
    markup = types.InlineKeyboardMarkup(row_width=1)
    if status == "pending":
        markup.add(
            types.InlineKeyboardButton("🔄 Взять в работу", callback_data=f"start_contract_{contract_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_contract_{contract_id}"),
        )
    elif status == "processing":
        markup.add(
            types.InlineKeyboardButton("📎 Прикрепить договор", callback_data=f"attach_contract_{contract_id}"),
            types.InlineKeyboardButton("✅ Завершить", callback_data=f"complete_contract_{contract_id}"),
        )
    elif status == "completed":
        markup.add(
            types.InlineKeyboardButton("📎 Просмотреть договор", callback_data=f"view_contract_file_{contract_id}"),
            types.InlineKeyboardButton("🔄 Переоткрыть", callback_data=f"reopen_contract_{contract_id}"),
        )
    markup.add(
        types.InlineKeyboardButton("👥 К списку пользователей", callback_data="admin_users"),
        types.InlineKeyboardButton("📋 К договорам", callback_data="admin_contracts"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"),
    )
    return markup


def _empty_contracts_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_users"))
    return markup


def _user_contract_detail_text(contract: dict) -> str:
    created_at = contract.get("created_at")
    completed_at = contract.get("completed_at")
    created = created_at.strftime("%d.%m.%Y %H:%M") if created_at else "дата не указана"
    completed = completed_at.strftime("%d.%m.%Y %H:%M") if completed_at else "не завершен"
    file_text = "Прикреплен" if contract.get("contract_file_id") else "Не прикреплен"
    return (
        f"📋 Детали договора #{contract['id']}\n\n"
        f"📄 Номер: {contract.get('contract_number')}\n"
        f"📋 Тип: {contract.get('contract_type')}\n"
        f"📅 Создан: {created}\n"
        f"✅ Завершен: {completed}\n"
        f"🔄 Статус: {_status_emoji(contract.get('status'))} {contract.get('status')}\n"
        f"📎 Файл договора: {file_text}\n"
    )


def _user_contract_detail_markup(contract: dict):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if contract.get("status") == "completed" and contract.get("contract_file_id"):
        markup.add(types.InlineKeyboardButton("📎 Скачать договор", callback_data=f"download_contract_{contract['id']}"))
    markup.add(types.InlineKeyboardButton("📋 К списку договоров", callback_data="my_contracts"))
    return markup


def _validate_contract_document(message) -> tuple[bool, str, str | None]:
    document = getattr(message, "document", None)
    if not document:
        return False, "❌ Пожалуйста, отправьте файл договора", None
    file_name = (getattr(document, "file_name", "") or "").lower()
    if not file_name.endswith(".txt"):
        return False, "❌ Файл должен быть в формате .txt", None
    if getattr(document, "file_size", 0) and document.file_size > 10 * 1024 * 1024:
        return False, "❌ Файл слишком большой. Максимум 10MB", None
    return True, "", document.file_id


def _refresh_admin_contract(bot, call, contract_id: int) -> None:
    contract = get_admin_contract(contract_id)
    if not contract:
        bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
        return
    bot.edit_message_text(
        _admin_contract_detail_text(contract),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=_admin_contract_detail_markup(contract),
    )


def register_admin_contract_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "admin_contracts")
    def handle_admin_contracts(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут управлять договорами", show_alert=True)
            return

        try:
            contracts = list_admin_contracts()
        except Exception as exc:
            logger.error("Error in admin contracts: %s", exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при получении договоров", show_alert=True)
            return

        if not contracts:
            bot.edit_message_text(
                "📋 Управление договорами\n\n❌ Нет активных договоров",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=_empty_contracts_markup(),
            )
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _admin_contracts_text(contracts),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_admin_contracts_markup(contracts),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_view_contract_"))
    def handle_admin_view_contract(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут просматривать договоры", show_alert=True)
            return

        try:
            contract_id = int(call.data.split("_")[3])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return

        try:
            contract = get_admin_contract(contract_id)
        except Exception as exc:
            logger.error("Error viewing contract %s: %s", contract_id, exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при просмотре договора", show_alert=True)
            return

        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _admin_contract_detail_text(contract),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_admin_contract_detail_markup(contract),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("view_contract_file_"))
    def handle_admin_view_contract_file(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут просматривать договоры", show_alert=True)
            return

        try:
            contract_id = int(call.data.split("_")[3])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return

        try:
            contract = get_admin_contract(contract_id)
        except Exception as exc:
            logger.error("Error loading contract file %s: %s", contract_id, exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при получении договора", show_alert=True)
            return

        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return

        file_id = contract.get("contract_file_id")
        if not file_id:
            bot.answer_callback_query(call.id, "❌ Файл договора не прикреплен", show_alert=True)
            return

        try:
            bot.send_document(
                call.message.chat.id,
                file_id,
                caption=(
                    f"📎 Договор #{contract_id}\n\n"
                    f"📄 Номер: {contract.get('contract_number')}\n"
                    f"📋 Тип: {contract.get('contract_type')}\n"
                    f"✅ Статус: {contract.get('status')}"
                ),
            )
            bot.answer_callback_query(call.id, "✅ Договор отправлен")
        except Exception as exc:
            logger.error("Error sending contract file %s: %s", contract_id, exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при отправке файла договора", show_alert=True)


    def process_contract_file(message, contract_id: int):
        if not _is_admin(message.from_user.id):
            bot.reply_to(message, "❌ Только администраторы могут прикреплять договоры")
            return
        is_valid, error_message, file_id = _validate_contract_document(message)
        if not is_valid:
            bot.reply_to(message, error_message)
            return
        try:
            contract = attach_contract_file(contract_id, file_id)
        except Exception as exc:
            logger.error("Error saving contract file %s: %s", contract_id, exc)
            bot.reply_to(message, "❌ Ошибка при сохранении файла")
            return
        if not contract:
            bot.reply_to(message, "❌ Договор не найден")
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Завершить договор", callback_data=f"complete_contract_{contract_id}"),
            types.InlineKeyboardButton("📋 К деталям договора", callback_data=f"admin_view_contract_{contract_id}"),
        )
        bot.reply_to(message, f"✅ Файл договора успешно прикреплен к договору #{contract_id}", reply_markup=markup)

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith("view_contract_") and not call.data.startswith("view_contract_file_")
    )
    def handle_legacy_view_contract(call):
        try:
            contract_or_release_id = int(call.data.split("_")[2])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return
        message_text = getattr(call.message, "text", "") or getattr(call.message, "caption", "") or ""
        should_open_user_contract = (
            "Ваши договоры" in message_text
            or "Детали договора" in message_text
            or user_owns_contract(contract_or_release_id, call.from_user.id)
        ) and "Полная информация о релизе" not in message_text
        if should_open_user_contract:
            contract = get_user_contract(contract_or_release_id, call.from_user.id)
            if contract:
                bot.answer_callback_query(call.id)
                bot.edit_message_text(
                    _user_contract_detail_text(contract),
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=_user_contract_detail_markup(contract),
                )
                return
        call.data = f"view_release_contract_{contract_or_release_id}"
        # Let the modular release file handler process future dedicated callbacks; for old ambiguous buttons send a clear hint.
        bot.answer_callback_query(call.id, "Откройте файл через карточку релиза", show_alert=True)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("start_contract_"))
    def handle_start_contract(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут управлять договорами", show_alert=True)
            return
        try:
            contract_id = int(call.data.split("_")[2])
            contract = update_contract_status(contract_id, "processing")
        except Exception as exc:
            logger.error("Error starting contract: %s", exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при изменении статуса", show_alert=True)
            return
        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        bot.answer_callback_query(call.id, "✅ Договор взят в работу", show_alert=True)
        _refresh_admin_contract(bot, call, contract_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("reopen_contract_"))
    def handle_reopen_contract(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут управлять договорами", show_alert=True)
            return
        try:
            contract_id = int(call.data.split("_")[2])
            contract = update_contract_status(contract_id, "processing")
        except Exception as exc:
            logger.error("Error reopening contract: %s", exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при изменении статуса", show_alert=True)
            return
        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        bot.answer_callback_query(call.id, "🔄 Договор снова в работе", show_alert=True)
        _refresh_admin_contract(bot, call, contract_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("reject_contract_"))
    def handle_reject_contract(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут управлять договорами", show_alert=True)
            return
        try:
            contract_id = int(call.data.split("_")[2])
            contract = update_contract_status(contract_id, "rejected")
        except Exception as exc:
            logger.error("Error rejecting contract: %s", exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при изменении статуса", show_alert=True)
            return
        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        bot.answer_callback_query(call.id, "❌ Договор отклонен", show_alert=True)
        _refresh_admin_contract(bot, call, contract_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("attach_contract_"))
    def handle_attach_contract(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут прикреплять договоры", show_alert=True)
            return
        try:
            contract_id = int(call.data.split("_")[2])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return
        if not hasattr(bot, "user_data"):
            bot.user_data = {}
        bot.user_data[call.from_user.id] = {"attaching_contract": contract_id}
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data=f"admin_view_contract_{contract_id}"))
        bot.edit_message_text(
            f"📎 Прикрепление договора #{contract_id}\n\n"
            "Отправьте файл договора в формате .txt\n\n"
            "⚠️ Важно: файл должен быть в формате .txt",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
        bot.register_next_step_handler(call.message, process_contract_file, contract_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("complete_contract_"))
    def handle_complete_contract(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут завершать договоры", show_alert=True)
            return
        try:
            contract_id = int(call.data.split("_")[2])
            contract = complete_contract(contract_id)
        except Exception as exc:
            logger.error("Error completing contract: %s", exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при завершении договора", show_alert=True)
            return
        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        if contract.get("missing_file"):
            bot.answer_callback_query(call.id, "❌ Сначала прикрепите файл договора", show_alert=True)
            return
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📋 Мои договоры", callback_data="my_contracts"))
            bot.send_message(
                contract["user_id"],
                f"✅ Ваш договор готов!\n\n"
                f"📋 Договор #{contract_id} был завершен администратором.\n"
                "📎 Файл договора прикреплен\n\n"
                "Просмотрите договор в разделе '📋 Получить договор'",
                reply_markup=markup,
            )
        except Exception as exc:
            logger.error("Failed to notify user %s: %s", contract.get("user_id"), exc)
        bot.answer_callback_query(call.id, "✅ Договор завершен", show_alert=True)
        _refresh_admin_contract(bot, call, contract_id)
