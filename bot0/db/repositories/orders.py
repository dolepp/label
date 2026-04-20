"""Order queries for modular bot code."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from db.pool import connection


def _row_to_order(row) -> dict[str, Any] | None:
    if row is None:
        return None
    order_id, user_id, service_type, amount, status, payment_id, created_date, updated_date, description, metadata = row
    return {
        "id": order_id,
        "user_id": user_id,
        "service_type": service_type,
        "amount": amount or Decimal("0"),
        "status": status or "pending",
        "payment_id": payment_id,
        "created_date": created_date,
        "updated_date": updated_date,
        "description": description,
        "metadata": metadata or {},
    }


def format_order_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if value is None:
        return "Дата не указана"
    try:
        return datetime.fromisoformat(str(value)).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(value)


def format_amount(value: Any) -> str:
    try:
        amount = Decimal(value or 0)
    except Exception:
        return str(value)
    if amount == amount.to_integral_value():
        return f"{int(amount)}₽"
    return f"{amount:.2f}₽"


def list_user_orders(user_id: int, limit: int = 10) -> list[dict[str, Any]]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id, user_id, service_type, amount, status, payment_id,
                    created_date, updated_date, description, metadata
                FROM orders
                WHERE user_id = %s
                ORDER BY created_date DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            return [_row_to_order(row) for row in cur.fetchall()]
        finally:
            cur.close()


def count_user_orders(user_id: int) -> int | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM orders WHERE user_id = %s", (user_id,))
            return cur.fetchone()[0]
        finally:
            cur.close()
