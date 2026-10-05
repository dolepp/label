"""Payment and balance persistence helpers for the legacy bot."""
from __future__ import annotations

from typing import Callable


def get_user_balance(
    user_id: int,
    get_connection: Callable,
    return_connection: Callable,
    logger,
) -> float:
    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            return 0.0

        cursor = conn.cursor()
        cursor.execute("SELECT COALESCE(balance, 0) FROM label WHERE telegram_id = %s", (user_id,))
        row = cursor.fetchone()
        return float(row[0]) if row else 0.0
    except Exception as exc:
        logger.error("Failed to get balance for %s: %s", user_id, exc)
        return 0.0
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_connection(conn)


def change_user_balance(
    user_id: int,
    delta: float,
    get_connection: Callable,
    return_connection: Callable,
    logger,
) -> bool:
    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            return False

        cursor = conn.cursor()
        if delta < 0:
            # Списание атомарно проверяет остаток: два параллельных списания не уведут баланс в минус.
            cursor.execute(
                "UPDATE label SET balance = COALESCE(balance,0) + %s WHERE telegram_id = %s AND COALESCE(balance,0) >= %s RETURNING balance",
                (delta, user_id, -delta),
            )
        else:
            cursor.execute(
                "UPDATE label SET balance = COALESCE(balance,0) + %s WHERE telegram_id = %s RETURNING balance",
                (delta, user_id),
            )
        updated = cursor.fetchone()
        conn.commit()
        if not updated:
            logger.warning("Balance change %s for %s was not applied (insufficient funds or no user)", delta, user_id)
        return bool(updated)
    except Exception as exc:
        logger.error("Failed to change balance for %s by %s: %s", user_id, delta, exc)
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_connection(conn)


def cancel_pending_topup_orders(
    user_id: int,
    get_connection: Callable,
    return_connection: Callable,
    logger,
) -> int:
    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            return 0

        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE orders
            SET status = 'cancelled'
            WHERE user_id = %s AND service_type = 'topup' AND status = 'pending'
            """,
            (user_id,),
        )
        conn.commit()
        return int(cursor.rowcount or 0)
    except Exception as exc:
        logger.error("Failed to cancel orders for user %s: %s", user_id, exc)
        return 0
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_connection(conn)
