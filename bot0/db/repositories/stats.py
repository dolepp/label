"""User-facing statistics queries."""
from __future__ import annotations

from decimal import Decimal

from db.pool import connection


def get_user_stats(user_id: int) -> dict | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM releases WHERE user_id = %s", (user_id,))
            releases_count = cur.fetchone()[0]

            cur.execute("SELECT COALESCE(balance, 0) FROM label WHERE telegram_id = %s", (user_id,))
            balance_row = cur.fetchone()
            balance = balance_row[0] if balance_row else Decimal("0")

            cur.execute(
                "SELECT COUNT(*) FROM orders WHERE user_id = %s AND status = %s",
                (user_id, "completed"),
            )
            completed_orders = cur.fetchone()[0]

            return {
                "releases_count": int(releases_count or 0),
                "balance": balance or Decimal("0"),
                "completed_orders": int(completed_orders or 0),
            }
        finally:
            cur.close()


def has_active_discount_promo(user_id: int) -> bool:
    with connection() as conn:
        if conn is None:
            return False
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT 1
                FROM user_discount_promos udp
                JOIN promo_codes pc ON pc.id = udp.promo_code_id AND pc.is_active = TRUE
                WHERE udp.user_id = %s
                  AND (pc.expires_at IS NULL OR pc.expires_at > CURRENT_TIMESTAMP)
                LIMIT 1
                """,
                (user_id,),
            )
            return cur.fetchone() is not None
        finally:
            cur.close()
