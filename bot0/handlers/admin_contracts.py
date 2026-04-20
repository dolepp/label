"""Admin contract list and detail handlers."""
from __future__ import annotations

import logging

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.admin_contracts import count_contract_statuses, get_admin_contract, list_admin_contracts
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
