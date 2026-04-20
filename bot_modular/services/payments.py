# -*- coding: utf-8 -*-
"""Сервис платежей: YooKassa, создание и проверка платежей."""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    from yookassa import Configuration, Payment
    YOOKASSA_AVAILABLE = True
except ImportError:
    YOOKASSA_AVAILABLE = False
    Payment = None
    Configuration = None


def init_yookassa():
    """Инициализация YooKassa"""
    try:
        from core.config import YOOKASSA_ACCOUNT_ID, YOOKASSA_SECRET_KEY
        Configuration.account_id = YOOKASSA_ACCOUNT_ID
        Configuration.secret_key = YOOKASSA_SECRET_KEY
        logger.info("✅ YooKassa configured")
        return True
    except Exception as e:
        logger.error(f"❌ YooKassa init failed: {e}")
        return False


def create_yookassa_payment(amount, user_id, service="topup", description=None, return_url="https://t.me/twaslabel_bot"):
    """
    Создать платёж YooKassa.
    Возвращает (payment_id, payment_url) или (None, None) при ошибке.
    """
    if not YOOKASSA_AVAILABLE or not Payment or not Configuration:
        logger.error("YooKassa module not available")
        return None, None
    if not Configuration.account_id or not Configuration.secret_key:
        logger.error("YooKassa credentials not set")
        return None, None
    if amount < 1 or amount > 1000000:
        logger.error(f"Invalid amount: {amount}")
        return None, None
    try:
        payment_data = {
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": return_url},
            "capture": True,
            "description": description or f"Оплата {service} для пользователя {user_id}",
            "metadata": {"user_id": str(user_id), "service": service}
        }
        payment = Payment.create(payment_data)
        return payment.id, payment.confirmation.confirmation_url
    except Exception as e:
        logger.error(f"YooKassa create payment failed: {e}")
        return None, None


def save_order_to_db(user_id, service_type, amount, payment_id):
    """Сохранить заказ в БД (orders). Возвращает True при успехе."""
    from utils.database import get_pg_connection, return_pg_connection
    conn = get_pg_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO orders (user_id, service_type, amount, status, payment_id, created_date) VALUES (%s, %s, %s, %s, %s, %s)',
            (user_id, service_type, amount, "pending", payment_id, datetime.now())
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Save order failed: {e}")
        return False
    finally:
        if conn:
            try:
                cursor.close()
                return_pg_connection(conn)
            except Exception:
                pass


def get_payment_status(payment_id):
    """Получить статус платежа в YooKassa. Возвращает status или None."""
    if not YOOKASSA_AVAILABLE or not Payment:
        return None
    try:
        payment = Payment.find_one(payment_id)
        return payment.status if payment else None
    except Exception as e:
        logger.error(f"Get payment status failed: {e}")
        return None
