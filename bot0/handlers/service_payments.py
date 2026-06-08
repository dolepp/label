"""Service payment callbacks migrated from label.py.

This module owns regular service `pay_*` and `check_payment_*` routing. It uses
injected runtime dependencies so it does not import the monolith.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Callable

from telebot import types

from handlers.service_selection import show_design_service as _default_show_design_service

logger = logging.getLogger(__name__)

bot = None
get_pg_connection: Callable[..., Any] | None = None
return_pg_connection: Callable[..., Any] | None = None
get_user_balance_safe: Callable[[int], float] | None = None
change_user_balance: Callable[[int, float], bool] | None = None
ensure_user_storage: Callable[[int], dict] | None = None
show_design_service: Callable[..., Any] | None = _default_show_design_service
handle_design_payment: Callable[..., Any] | None = None
handle_successful_payment: Callable[..., Any] | None = None
Payment = None
DESIGN_BRIEF_TEMPLATES: dict[str, Any] = {}

SERVICE_PRICES = {
    "distribution": 1299,
    "cover": 2000,
    "motion": 1500,
    "videoshot": 1000,
}


def configure_service_payments(**context: Any) -> None:
    globals().update({key: value for key, value in context.items() if value is not None})


def _require(name: str) -> Any:
    value = globals().get(name)
    if value is None:
        raise RuntimeError(f"service payment dependency is not configured: {name}")
    return value


def _is_service_pay_callback(call) -> bool:
    data = getattr(call, "data", "") or ""
    return data.startswith("pay_") and not data.startswith("pay_stars_")


def handle_payment(call):
    """Handle balance payment for services."""
    active_bot = _require("bot")
    service = call.data.split("_")[1]
    user_id = call.from_user.id

    price = SERVICE_PRICES.get(service)
    if not price:
        active_bot.answer_callback_query(call.id, "Неверный тип услуги")
        return

    templates = DESIGN_BRIEF_TEMPLATES or {}
    if service in templates:
        storage = _require("ensure_user_storage")(user_id)
        briefs = storage.get("design_briefs", {})
        if service not in briefs:
            active_bot.answer_callback_query(call.id, "Сначала заполните бриф для этой услуги.", show_alert=True)
            _require("show_design_service")(call.message, service)
            return

    promo = None
    conn = _require("get_pg_connection")()
    cursor = None
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT code, discount FROM promo_codes WHERE service_type = %s AND current_activations < max_activations",
                (service,),
            )
            promo = cursor.fetchone()
        except Exception as exc:
            logger.error("PostgreSQL error in handle_payment promo check: %s", exc)
            promo = None
        finally:
            try:
                if cursor:
                    cursor.close()
                _require("return_pg_connection")(conn)
            except Exception:
                pass
    else:
        logger.warning("Database unavailable for promo check; skipping")

    try:
        if promo:
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("💳 Оплатить без промокода", callback_data=f"confirm_pay_{service}"),
                types.InlineKeyboardButton("🎟 Ввести промокод", callback_data=f"promo_{service}"),
                types.InlineKeyboardButton("◀️ Отмена", callback_data="services_back"),
            )
            active_bot.edit_message_text(
                f"💰 Сумма к оплате: {price}₽\n\nУ вас есть промокод?",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
            )
            return

        balance = _require("get_user_balance_safe")(user_id)
        if balance >= price:
            if _require("change_user_balance")(user_id, -price):
                active_bot.answer_callback_query(call.id, f"✅ Списано {price}₽ с баланса")
                conn2 = _require("get_pg_connection")()
                cur2 = None
                if conn2:
                    try:
                        cur2 = conn2.cursor()
                        cur2.execute(
                            "INSERT INTO orders (user_id, service_type, amount, status, payment_id, created_date) VALUES (%s, %s, %s, %s, %s, %s)",
                            (user_id, service, price, "completed", f"balance-{uuid.uuid4()}", datetime.now()),
                        )
                        conn2.commit()
                    except Exception as exc:
                        logger.error("Failed to create balance order: %s", exc)
                    finally:
                        try:
                            if cur2:
                                cur2.close()
                            _require("return_pg_connection")(conn2)
                        except Exception:
                            pass
                payment = type(
                    "PaymentLike",
                    (object,),
                    {
                        "id": f"balance-{uuid.uuid4()}",
                        "amount": type("AmountLike", (object,), {"value": price})(),
                        "metadata": {"user_id": str(user_id)},
                    },
                )()
                _require("handle_design_payment")(call, payment, service)
            else:
                active_bot.answer_callback_query(call.id, "❌ Не удалось списать средства с баланса", show_alert=True)
            return

        need = int(price - balance)
        getattr(active_bot, "user_data", {}).setdefault(user_id, {})["pending_operation"] = {
            "type": service,
            "amount": price,
            "needed": need,
            "resume": True,
        }
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(f"Пополнить на {need}₽", callback_data=f"topup_pay_{need}"),
            types.InlineKeyboardButton("❌ Отмена", callback_data="services_back"),
        )
        active_bot.edit_message_text(
            f"❌ Недостаточно средств для оплаты услуги {service}.\nТребуется {price}₽, на балансе {balance:,.2f}₽.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
    except Exception as exc:
        logger.error("PostgreSQL error in handle_payment: %s", exc)
        active_bot.answer_callback_query(call.id, "❌ Произошла ошибка при обработке платежа.", show_alert=True)


def create_payment(call, service, amount):
    """Create payment using YooKassa."""
    active_bot = _require("bot")
    payment_api = _require("Payment")
    payment = payment_api.create({
        "amount": {"value": str(amount), "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": "https://t.me/twaslabel_bot"},
        "capture": True,
        "description": f"Оплата услуги {service} в TWAS Label",
        "metadata": {"user_id": str(call.from_user.id), "service": service},
    })
    payment_url = payment.confirmation.confirmation_url
    payment_id = payment.id

    conn = _require("get_pg_connection")()
    cursor = None
    if not conn:
        active_bot.edit_message_text(
            "❌ Ошибка подключения к базе данных. Не удалось сохранить информацию о платеже.",
            call.message.chat.id,
            call.message.message_id,
        )
        return
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (user_id, service_type, amount, status, payment_id, created_date) VALUES (%s, %s, %s, %s, %s, %s)",
            (call.from_user.id, service, amount, "pending", payment_id, datetime.now()),
        )
        conn.commit()
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("💳 Перейти к оплате", url=payment_url),
            types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_payment_{payment_id}"),
        )
        active_bot.edit_message_text(
            f"💰 Сумма к оплате: {amount}₽\n\n"
            "Нажмите кнопку ниже для перехода к оплате.\n"
            "После оплаты нажмите 'Проверить оплату'.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
    except Exception as exc:
        logger.error("PostgreSQL error in create_payment: %s", exc)
        active_bot.edit_message_text(
            "❌ Произошла ошибка при создании платежа. Попробуйте позже.",
            call.message.chat.id,
            call.message.message_id,
        )
    finally:
        if conn:
            if cursor:
                cursor.close()
            _require("return_pg_connection")(conn)


def check_payment_status(call):
    """Check YooKassa payment status and delegate successful handling."""
    active_bot = _require("bot")
    payment_api = _require("Payment")
    payment_id = call.data.split("_")[2]
    user_id = call.from_user.id

    try:
        active_bot.answer_callback_query(call.id, "🔎 Проверяю оплату...")
    except Exception:
        pass

    conn = _require("get_pg_connection")()
    cursor = None
    if not conn:
        active_bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT amount, service_type, status, user_id FROM orders WHERE payment_id = %s", (payment_id,))
        order_info = cursor.fetchone()

        if not order_info:
            try:
                payment = payment_api.find_one(payment_id)
                if payment and hasattr(payment, "metadata") and payment.metadata.get("order_id"):
                    original_order_id = payment.metadata["order_id"]
                    cursor.execute("SELECT amount, service_type, status, user_id FROM orders WHERE payment_id = %s", (original_order_id,))
                    order_info = cursor.fetchone()
                    logger.info("Found order via YooKassa metadata: %s", original_order_id)
            except Exception as exc:
                logger.error("Failed to get payment metadata: %s", exc)

        if not order_info:
            logger.error("Order not found for payment_id: %s", payment_id)
            active_bot.answer_callback_query(call.id, "❌ Заказ не найден в базе данных", show_alert=True)
            return

        amount, service_type, order_status, order_user_id = order_info
        if order_user_id != user_id:
            logger.warning("User %s trying to check payment for order owned by %s", user_id, order_user_id)
            active_bot.answer_callback_query(call.id, "❌ Это не ваш заказ", show_alert=True)
            return

        if order_status == "completed":
            active_bot.answer_callback_query(call.id, "✅ Этот заказ уже оплачен и обработан", show_alert=True)
            return

        payment = None
        try:
            payment = payment_api.find_one(payment_id)
            logger.info("Payment %s status: %s", payment_id, getattr(payment, "status", "unknown"))
        except Exception as exc:
            logger.error("Error fetching payment %s from YooKassa: %s", payment_id, exc)
            try:
                cursor.execute("SELECT created_date FROM orders WHERE payment_id = %s", (payment_id,))
                created_date_result = cursor.fetchone()
                if created_date_result:
                    created_date = created_date_result[0]
                    if (datetime.now() - created_date).total_seconds() > 3600:
                        active_bot.answer_callback_query(call.id, "❌ Время ожидания платежа истекло. Создайте новый заказ.", show_alert=True)
                        return
            except Exception as date_error:
                logger.error("Error checking order date: %s", date_error)
            active_bot.answer_callback_query(call.id, "❌ Не удалось проверить статус платежа. Попробуйте позже.", show_alert=True)
            return

        if not payment:
            active_bot.answer_callback_query(call.id, "❌ Платеж не найден в системе YooKassa", show_alert=True)
            return

        status = getattr(payment, "status", None)
        logger.info("Payment %s final status: %s", payment_id, status)
        if status == "succeeded":
            _require("handle_successful_payment")(call, payment)
        elif status in ("pending", "waiting_for_capture", "waiting_for_payment"):
            active_bot.answer_callback_query(call.id, "⏳ Оплата еще не получена. Попробуйте позже.", show_alert=True)
        elif status == "canceled":
            active_bot.answer_callback_query(call.id, "❌ Платеж отменен", show_alert=True)
        else:
            active_bot.answer_callback_query(call.id, f"❌ Статус платежа: {status}", show_alert=True)
    except Exception as exc:
        logger.error("Error in check_payment_status: %s", exc)
        active_bot.answer_callback_query(call.id, "❌ Ошибка при проверке платежа", show_alert=True)
    finally:
        if conn:
            if cursor:
                cursor.close()
            _require("return_pg_connection")(conn)


def register_service_payment_handlers(bot, context: dict | None = None) -> None:
    configure_service_payments(bot=bot, **(context or {}))

    @bot.callback_query_handler(func=_is_service_pay_callback)
    def service_payment_callback(call):
        handle_payment(call)

    @bot.callback_query_handler(func=lambda call: (getattr(call, "data", "") or "").startswith("check_payment_"))
    def service_check_payment_callback(call):
        check_payment_status(call)
