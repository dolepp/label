"""Finance summary queries for modular bot code."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from db.pool import connection


def get_user_finance_summary(user_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    COALESCE(l.balance, 0) AS balance,
                    COUNT(o.id) AS total_orders,
                    COUNT(o.id) FILTER (WHERE o.status = 'completed') AS completed_orders,
                    COALESCE(SUM(o.amount) FILTER (WHERE o.status = 'completed'), 0) AS completed_sum,
                    COUNT(o.id) FILTER (WHERE o.status = 'pending') AS pending_orders,
                    COUNT(o.id) FILTER (WHERE o.status = 'cancelled') AS cancelled_orders
                FROM label l
                LEFT JOIN orders o ON l.telegram_id = o.user_id
                WHERE l.telegram_id = %s
                GROUP BY l.telegram_id, l.balance
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            balance, total_orders, completed_orders, completed_sum, pending_orders, cancelled_orders = row
            return {
                "balance": balance or Decimal("0"),
                "total_orders": int(total_orders or 0),
                "completed_orders": int(completed_orders or 0),
                "completed_sum": completed_sum or Decimal("0"),
                "pending_orders": int(pending_orders or 0),
                "cancelled_orders": int(cancelled_orders or 0),
            }
        finally:
            cur.close()


def find_user_id_by_username(username: str) -> int | None:
    normalized = (username or "").strip().lstrip("@")
    if not normalized:
        return None
    with connection() as conn:
        if conn is None:
            raise ConnectionError("PostgreSQL connection unavailable")
        cur = conn.cursor()
        try:
            cur.execute("SELECT telegram_id FROM label WHERE tg = %s", (normalized,))
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            cur.close()


def add_balance_transaction(user_id: int, amount, description: str) -> dict:
    with connection() as conn:
        if conn is None:
            raise ConnectionError("PostgreSQL connection unavailable")
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE label SET balance = COALESCE(balance, 0) + %s WHERE telegram_id = %s RETURNING tg",
                (amount, user_id),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                raise ValueError("Пользователь не найден")
            cur.execute(
                """
                INSERT INTO transactions (user_id, amount, description, created_date)
                VALUES (%s, %s, %s, NOW())
                """,
                (user_id, amount, description),
            )
            conn.commit()
            return {"user_id": user_id, "username": row[0], "amount": amount, "description": description}
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
