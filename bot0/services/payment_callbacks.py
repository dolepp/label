"""Successful service payment callbacks detached from label.py."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Callable

from core.config import PERMANENT_ADMINS
from handlers.design_admin import build_design_status_markup, format_design_request_text
from handlers.legacy_distribution_steps import save_release_data_for_user
from services import notifications

logger = logging.getLogger(__name__)

bot = None
get_pg_connection: Callable[..., Any] | None = None
return_pg_connection: Callable[..., Any] | None = None
get_user_balance_safe: Callable[[int], float] | None = None
change_user_balance: Callable[[int, float], bool] | None = None
ensure_user_storage: Callable[[int], dict] | None = None
DESIGN_BRIEF_REQUESTS: list[dict[str, Any]] = []
SERVICE_LABELS: dict[str, str] = {}


def configure(**context: Any) -> None:
    globals().update({key: value for key, value in context.items() if value is not None})


def _require(name: str) -> Any:
    value = globals().get(name)
    if value is None:
        raise RuntimeError(f"payment callback dependency is not configured: {name}")
    return value



def generate_request_id() -> str:
    return uuid.uuid4().hex[:8]


def get_display_username(user) -> str:
    if not user:
        return "Без имени"
    username = getattr(user, "username", None)
    if username:
        return f"@{username}"
    first_name = getattr(user, "first_name", None)
    user_id = getattr(user, "id", None)
    return str(first_name or user_id or user)


def notify_admins_design(order: dict) -> None:
    active_bot = _require("bot")
    text = format_design_request_text(order)
    markup = build_design_status_markup(order["id"], order["status"])
    for admin_id in PERMANENT_ADMINS:
        try:
            active_bot.send_message(admin_id, text, reply_markup=markup)
        except Exception as exc:
            logger.error("Failed to send design order to admin %s: %s", admin_id, exc)

def notify_admins(message, levels):
    notifications.notify_order_admins(
        _require("bot"),
        message,
        _require("get_pg_connection"),
        _require("return_pg_connection"),
        logger,
    )


def handle_distribution_payment(call, payment):
    active_bot = _require("bot")
    try:
        active_bot.edit_message_text(
            "🎉 Оплата прошла успешно! Мы начнем работать над вашим релизом.",
            call.message.chat.id,
            call.message.message_id,
        )
        admin_message = (
            "💰 Новый оплаченный заказ дистрибуции!\n\n"
            f"Клиент: {payment.metadata['user_id']}\n"
            f"Сумма: {payment.amount.value}₽"
        )
        notify_admins(admin_message, [])
        logger.info("Successfully processed distribution payment %s", payment.id)
    except Exception as exc:
        logger.error("Error in handle_distribution_payment: %s", exc)
        try:
            active_bot.send_message(call.message.chat.id, "🎉 Оплата прошла успешно! Мы начнем работать над вашим релизом.")
        except Exception:
            pass


def _ensure_user_exists_and_get_info(cursor, conn, user_id: int):
    cursor.execute("SELECT tg, name FROM label WHERE telegram_id = %s", (user_id,))
    user_info = cursor.fetchone()
    if not user_info:
        try:
            cursor.execute(
                """
                INSERT INTO label (telegram_id, created_date, balance, artist)
                VALUES (%s, CURRENT_TIMESTAMP, 0, 1)
                ON CONFLICT (telegram_id) DO NOTHING
                """,
                (user_id,),
            )
            conn.commit()
            logger.info("Created new user record for %s during payment processing", user_id)
            cursor.execute("SELECT tg, name FROM label WHERE telegram_id = %s", (user_id,))
            user_info = cursor.fetchone()
        except Exception as exc:
            logger.error("Failed to create user record during payment: %s", exc)
            return None, None
    return (user_info[0] if user_info else None, user_info[1] if user_info else None)


def _resume_pending_operation(call, cursor, conn, user_id: int, artist_name, username) -> None:
    active_bot = _require("bot")
    pending = getattr(active_bot, "user_data", {}).get(user_id, {}).get("pending_operation")
    if not pending or not isinstance(pending, dict):
        return
    try:
        new_balance = _require("get_user_balance_safe")(user_id)
        required = float(pending.get("amount", 0))
        if new_balance < required:
            active_bot.send_message(
                call.message.chat.id,
                f"❌ Недостаточно средств для завершения операции. Требуется {required}₽, на балансе {new_balance:,.2f}₽. Пополните баланс и нажмите 'Проверить оплату'.",
            )
            return
        if not _require("change_user_balance")(user_id, -required):
            active_bot.send_message(call.message.chat.id, "❌ Не удалось списать средства с баланса для продолжения операции.")
            return

        op_type = pending.get("type")
        if op_type == "distribution":
            save_release_data_for_user(user_id, call.message.chat.id)
        elif op_type in ("cover", "motion", "videoshot"):
            active_bot.send_message(call.message.chat.id, f"✅ Оплата услуги {op_type} с баланса завершена")
            try:
                cursor.execute(
                    "INSERT INTO orders (user_id, service_type, amount, status, payment_id, created_date) VALUES (%s, %s, %s, %s, %s, %s)",
                    (user_id, op_type, required, "completed", f"balance-{uuid.uuid4()}", datetime.now()),
                )
                conn.commit()
                logger.info("Created balance order for %s service, user %s, amount %s", op_type, user_id, required)
            except Exception as exc:
                logger.error("Failed to record balance order for %s: %s", user_id, exc)
            admin_message = (
                f"💰 Новый заказ {op_type} оплачен с баланса!\n\n"
                f"Клиент: {artist_name or 'Неизвестный артист'} (@{username or 'Неизвестный пользователь'})\n"
                f"Сумма: {required}₽"
            )
            notify_admins(admin_message, [])
        try:
            active_bot.user_data[user_id].pop("pending_operation", None)
            logger.info("Cleared pending operation for user %s", user_id)
        except Exception:
            pass
    except Exception as exc:
        logger.error("Error resuming pending operation for %s: %s", user_id, exc)
        active_bot.send_message(call.message.chat.id, "❌ Ошибка при возобновлении операции. Обратитесь в поддержку.")


def handle_successful_payment(call, payment):
    active_bot = _require("bot")
    service = payment.metadata["service"]
    user_id = int(payment.metadata["user_id"])

    conn = _require("get_pg_connection")()
    if not conn:
        active_bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных. Не удалось обработать платеж.", show_alert=True)
        return

    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = %s WHERE payment_id = %s", ("completed", payment.id))
        conn.commit()
        username, artist_name = _ensure_user_exists_and_get_info(cursor, conn, user_id)

        if service != "topup":
            notify_admins(
                "💰 Новый оплаченный заказ!\n\n"
                f"Услуга: {service}\n"
                f"Клиент: {artist_name or 'Неизвестный артист'} (@{username or 'Неизвестный пользователь'})\n"
                f"Сумма: {payment.amount.value}₽",
                [],
            )

        if service == "topup":
            try:
                cursor.execute("UPDATE label SET balance = COALESCE(balance,0) + %s WHERE telegram_id = %s", (float(payment.amount.value), user_id))
                conn.commit()
                logger.info("Successfully updated balance for user %s: +%s₽", user_id, payment.amount.value)
            except Exception as exc:
                logger.error("Failed to update balance for user %s: %s", user_id, exc)
                active_bot.answer_callback_query(call.id, "❌ Ошибка при зачислении баланса", show_alert=True)
                return
            try:
                active_bot.edit_message_text(f"✅ Баланс пополнен на {payment.amount.value}₽", call.message.chat.id, call.message.message_id)
            except Exception:
                active_bot.send_message(call.message.chat.id, f"✅ Баланс пополнен на {payment.amount.value}₽")
            try:
                active_bot.answer_callback_query(call.id, "✅ Оплата подтверждена, баланс пополнен")
            except Exception:
                pass
            _resume_pending_operation(call, cursor, conn, user_id, artist_name, username)
        elif service == "distribution":
            handle_distribution_payment(call, payment)
        else:
            handle_design_payment(call, payment, service)
        logger.info("Successfully processed payment %s for user %s, service: %s", payment.id, user_id, service)
    except Exception as exc:
        logger.error("Unexpected error in handle_successful_payment: %s", exc)
        active_bot.answer_callback_query(call.id, "❌ Произошла неожиданная ошибка при обработке платежа.", show_alert=True)
    finally:
        if conn:
            if cursor:
                cursor.close()
            _require("return_pg_connection")(conn)


def handle_design_payment(call, payment, service):
    active_bot = _require("bot")
    try:
        user_id = int(payment.metadata.get("user_id", call.from_user.id)) if hasattr(payment, "metadata") else call.from_user.id
        user_display = get_display_username(call.from_user)
        active_bot.edit_message_text(
            "🎉 Оплата прошла успешно! Мы начнем работать над вашим дизайном.",
            call.message.chat.id,
            call.message.message_id,
        )

        storage = _require("ensure_user_storage")(user_id)
        briefs = storage.get("design_briefs", {})
        brief_text = briefs.pop(service, None)
        order_entry = {
            "id": generate_request_id(),
            "service": service,
            "details": brief_text or "Бриф не был заполнен",
            "status": "принят",
            "user_id": user_id,
            "chat_id": call.message.chat.id,
            "user_display": user_display,
            "created_at": datetime.now().isoformat(),
        }
        DESIGN_BRIEF_REQUESTS.append(order_entry)
        notify_admins_design(order_entry)

        service_label = SERVICE_LABELS.get(service, service)
        notify_admins(
            f"💰 Новый оплаченный заказ {service_label}!\n\n"
            f"Клиент: {user_display} (ID: {user_id})\n"
            f"Сумма: {payment.amount.value}₽\n\n"
            f"Описание:\n{brief_text or 'Бриф не был заполнен'}",
            [],
        )
        logger.info("Successfully processed design payment %s for service %s", payment.id, service)
    except Exception as exc:
        logger.error("Error in handle_design_payment: %s", exc)
        try:
            active_bot.send_message(call.message.chat.id, "🎉 Оплата прошла успешно! Мы начнем работать над вашим дизайном.")
        except Exception:
            pass
