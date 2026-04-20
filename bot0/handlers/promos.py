"""User promo code handlers for the modular bot."""
from __future__ import annotations

import logging
from decimal import Decimal

from db.repositories.promos import activate_promo
from keyboards.reply import create_cancel_keyboard, create_profile_menu


logger = logging.getLogger(__name__)


def _profile_markup():
    return create_profile_menu(include_referral=False)


def _cancel_markup():
    return create_cancel_keyboard()


def _format_amount(value: Decimal) -> str:
    if value == value.to_integral_value():
        return f"{int(value):,}".replace(",", " ")
    return f"{value:,.2f}".replace(",", " ")


def _reply_for_result(result: dict) -> str:
    status = result.get("status")
    if status == "empty":
        return "❌ Введите промокод."
    if status == "not_found":
        return "❌ Промокод не найден или неактивен."
    if status == "expired":
        return "❌ Промокод истек."
    if status == "limit_reached":
        return "❌ Промокод достиг лимита использований."
    if status == "already_used":
        return "❌ Вы уже использовали этот промокод."
    if status == "discount_already_active":
        return "❌ Вы уже активировали этот промокод на скидку. Он будет доступен при оплате дистрибуции."
    if status == "invalid":
        return "❌ Промокод некорректен: в нем нет суммы пополнения или скидки."
    if status == "db_unavailable":
        return "❌ Ошибка подключения к базе данных."
    if status == "discount_activated":
        discount = Decimal(result.get("discount") or 0)
        return (
            "✅ Промокод на скидку активирован!\n\n"
            f"Скидка {discount:.0f}% будет доступна при оплате дистрибуции."
        )
    if status == "balance_activated":
        amount = Decimal(result.get("amount") or 0)
        return f"✅ Промокод активирован!\n\nНа ваш баланс зачислено: {_format_amount(amount)}₽"
    return "❌ Не удалось активировать промокод."


def register_promo_handlers(bot) -> None:
    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "🎟 Ввести промокод")
    def handle_promo_input(message):
        sent = bot.reply_to(
            message,
            "🎟 Ввод промокода\n\nВведите ваш промокод:",
            reply_markup=_cancel_markup(),
        )
        bot.register_next_step_handler(sent, process_promo_input)

    @bot.callback_query_handler(func=lambda call: call.data == "promo_from_profile")
    def handle_promo_from_profile(call):
        bot.answer_callback_query(call.id)
        sent = bot.send_message(
            call.message.chat.id,
            "🎟 Ввод промокода\n\nВведите ваш промокод:",
            reply_markup=_cancel_markup(),
        )
        bot.register_next_step_handler(sent, process_promo_input)

    def process_promo_input(message):
        text = (getattr(message, "text", "") or "").strip()
        if text.lower() in {"/cancel", "отмена", "❌ отмена", "cancel"}:
            bot.reply_to(message, "Возвращаемся в профиль", reply_markup=_profile_markup())
            return

        try:
            result = activate_promo(message.from_user.id, text)
        except Exception as exc:
            logger.error("Could not activate promo for user %s: %s", message.from_user.id, exc)
            bot.reply_to(message, "❌ Ошибка активации промокода. Попробуйте позже.", reply_markup=_profile_markup())
            return

        bot.reply_to(message, _reply_for_result(result), reply_markup=_profile_markup())
