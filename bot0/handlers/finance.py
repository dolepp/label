"""Finance profile handlers for the modular bot."""
from __future__ import annotations

import logging
from decimal import Decimal

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.finance import add_balance_transaction, find_user_id_by_username, get_user_finance_summary
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


def _transaction_notification(amount, description: str) -> str:
    return (
        "💰 Новое начисление\n\n"
        f"Сумма: {float(amount):+,.2f}₽\n"
        f"Описание: {description}\n\n"
        "Проверить баланс можно в разделе 'Мои финансы'"
    )


def _money(value) -> str:
    amount = Decimal(value or 0)
    return f"{amount:,.2f}".replace(",", " ")


def _finance_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("💳 Пополнить", callback_data="topup_from_profile"))
    markup.add(types.InlineKeyboardButton("🎟 Промокод", callback_data="promo_from_profile"))
    markup.add(types.InlineKeyboardButton("🛒 Мои заказы", callback_data="profile_orders"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_profile"))
    return markup


def _finance_text(summary: dict) -> str:
    return (
        "💰 Ваши финансы:\n\n"
        f"💳 Баланс: {_money(summary['balance'])}₽\n"
        f"📊 Всего заказов: {summary['total_orders']}\n"
        f"✅ Завершенных: {summary['completed_orders']}\n"
        f"⏳ Ожидают оплаты: {summary['pending_orders']}\n"
        f"🚫 Отмененных: {summary['cancelled_orders']}\n"
        f"💵 Оплачено всего: {_money(summary['completed_sum'])}₽"
    )


def register_finance_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "profile_finance")
    def handle_profile_finance(call):
        summary = get_user_finance_summary(call.from_user.id)
        if summary is None:
            bot.answer_callback_query(call.id, "❌ Финансовая информация не найдена", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _finance_text(summary),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_finance_markup(),
        )


    def process_finance_command(message):
        try:
            username, amount_raw, *description_parts = (message.text or "").split()
            if not username.startswith("@"):
                raise ValueError("Username должен начинаться с @")
            amount = Decimal(amount_raw.replace(",", "."))
            description = " ".join(description_parts).strip()
            if not description:
                raise ValueError("Описание не может быть пустым")

            target_user_id = find_user_id_by_username(username)
            if not target_user_id:
                bot.reply_to(message, f"❌ Пользователь {username} не найден")
                return

            tx = add_balance_transaction(target_user_id, amount, description)
            try:
                bot.send_message(target_user_id, _transaction_notification(amount, description))
            except Exception as exc:
                logger.error("Failed to send transaction notification to user %s: %s", tx.get("username"), exc)

            bot.reply_to(
                message,
                "✅ Начисление выполнено\n\n"
                f"Пользователь: {username}\n"
                f"Сумма: {float(amount):+,.2f}₽\n"
                f"Описание: {description}",
            )
        except ValueError as exc:
            bot.reply_to(message, f"❌ Ошибка: {exc}\n\nИспользуйте формат:\n@username сумма описание")
        except Exception as exc:
            logger.error("Error processing finance command: %s", exc)
            bot.reply_to(message, f"❌ Произошла непредвиденная ошибка: {exc}")

    @bot.message_handler(commands=["finance"])
    def handle_finance_command(message):
        if not _is_admin(message.from_user.id):
            bot.reply_to(message, "❌ У вас нет доступа к этой команде")
            return
        bot.reply_to(
            message,
            "Введите данные в формате:\n"
            "@username сумма описание\n\n"
            "Например: @user 1000 Начисление за стриминг",
        )
        bot.register_next_step_handler(message, process_finance_command)
