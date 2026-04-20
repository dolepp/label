"""User contract list, detail, and download handlers."""
from __future__ import annotations

import logging

from telebot import types

from db.repositories.contracts import get_user_contract, list_user_contracts


logger = logging.getLogger(__name__)


def _status_emoji(status: str | None) -> str:
    return {
        "pending": "⏳",
        "processing": "🔄",
        "completed": "✅",
        "rejected": "❌",
    }.get(status, "❓")


def _format_contract_button(contract: dict) -> str:
    created_at = contract.get("created_at")
    created = created_at.strftime("%d.%m.%Y %H:%M") if created_at else "дата не указана"
    return f"{_status_emoji(contract.get('status'))} {contract.get('contract_number')} ({created})"


def _contracts_list_text(contracts: list[dict]) -> str:
    if not contracts:
        return "📋 У вас пока нет договоров\n\n💡 Создайте новый договор в разделе '📋 Получить договор'"
    return "📋 Ваши договоры:\n\n"


def _contract_detail_text(contract: dict) -> str:
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


def _contracts_list_markup(contracts: list[dict]):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if contracts:
        for contract in contracts:
            markup.add(
                types.InlineKeyboardButton(
                    _format_contract_button(contract),
                    callback_data=f"view_user_contract_{contract['id']}",
                )
            )
        markup.add(types.InlineKeyboardButton("📋 Создать новый договор", callback_data="create_contract"))
    else:
        markup.add(types.InlineKeyboardButton("📋 Создать договор", callback_data="create_contract"))
    markup.add(types.InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_main"))
    return markup


def _contract_detail_markup(contract: dict):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if contract.get("status") == "completed" and contract.get("contract_file_id"):
        markup.add(types.InlineKeyboardButton("📎 Скачать договор", callback_data=f"download_contract_{contract['id']}"))
    markup.add(
        types.InlineKeyboardButton("📋 К списку договоров", callback_data="my_contracts"),
        types.InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_main"),
    )
    return markup


def _download_caption(contract: dict) -> str:
    return (
        f"📎 Договор #{contract['id']}\n\n"
        f"📄 Номер: {contract.get('contract_number')}\n"
        f"📋 Тип: {contract.get('contract_type')}\n"
        "✅ Статус: Завершен"
    )


def register_contract_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "my_contracts")
    def handle_my_contracts(call):
        try:
            contracts = list_user_contracts(call.from_user.id)
        except Exception as exc:
            logger.error("Error fetching contracts for user %s: %s", call.from_user.id, exc)
            bot.answer_callback_query(call.id, "❌ Произошла ошибка при получении списка договоров.", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _contracts_list_text(contracts),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_contracts_list_markup(contracts),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("view_user_contract_"))
    def handle_view_contract(call):
        try:
            contract_id = int(call.data.split("_")[3])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return

        try:
            contract = get_user_contract(contract_id, call.from_user.id)
        except Exception as exc:
            logger.error("Error viewing contract %s: %s", contract_id, exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при просмотре договора", show_alert=True)
            return

        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден или недоступен", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _contract_detail_text(contract),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_contract_detail_markup(contract),
        )

        if contract.get("status") == "completed" and contract.get("contract_file_id"):
            try:
                bot.send_document(call.message.chat.id, contract["contract_file_id"], caption=_download_caption(contract))
            except Exception as exc:
                logger.error("Error sending contract file %s: %s", contract_id, exc)
                bot.answer_callback_query(call.id, "❌ Ошибка при отправке файла договора", show_alert=True)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("download_contract_"))
    def handle_download_contract(call):
        try:
            contract_id = int(call.data.split("_")[2])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return

        try:
            contract = get_user_contract(contract_id, call.from_user.id)
        except Exception as exc:
            logger.error("Error downloading contract %s: %s", contract_id, exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при получении договора", show_alert=True)
            return

        if not contract or contract.get("status") != "completed":
            bot.answer_callback_query(call.id, "❌ Договор не найден или недоступен", show_alert=True)
            return

        if not contract.get("contract_file_id"):
            bot.answer_callback_query(call.id, "❌ Файл договора не прикреплен", show_alert=True)
            return

        try:
            bot.send_document(call.message.chat.id, contract["contract_file_id"], caption=_download_caption(contract))
            bot.answer_callback_query(call.id, "✅ Договор отправлен", show_alert=False)
        except Exception as exc:
            logger.error("Error sending contract file %s: %s", contract_id, exc)
            bot.answer_callback_query(call.id, "❌ Ошибка при отправке файла договора", show_alert=True)
