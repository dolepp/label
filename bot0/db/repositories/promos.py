"""Promo code queries and activation logic for modular bot code."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from db.pool import connection


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(value or 0)
    except Exception:
        return Decimal("0")


def _limit_reached(limit: int | None, current: int | None) -> bool:
    return limit is not None and int(current or 0) >= int(limit)


def _new_current(current: int | None) -> int:
    return int(current or 0) + 1


def _ensure_user(cur, user_id: int) -> None:
    cur.execute("SELECT id FROM label WHERE telegram_id = %s LIMIT 1", (user_id,))
    if cur.fetchone():
        return
    cur.execute(
        """
        INSERT INTO label (telegram_id, created_date, balance)
        VALUES (%s, CURRENT_TIMESTAMP, 0)
        """,
        (user_id,),
    )


def _ensure_discount_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_discount_promos (
            user_id BIGINT NOT NULL,
            promo_code_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, promo_code_id),
            FOREIGN KEY (promo_code_id) REFERENCES promo_codes(id) ON DELETE CASCADE
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_user_discount_promos_user_id ON user_discount_promos(user_id)")


def get_promo_counts() -> dict[str, int]:
    with connection() as conn:
        if conn is None:
            return {}
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE is_active = TRUE) AS active,
                    COUNT(*) FILTER (WHERE COALESCE(discount, 0) > 0) AS discount,
                    COUNT(*) FILTER (WHERE COALESCE(amount, 0) > 0) AS balance
                FROM promo_codes
                """
            )
            total, active, discount, balance = cur.fetchone()
            return {
                "total": int(total or 0),
                "active": int(active or 0),
                "discount": int(discount or 0),
                "balance": int(balance or 0),
            }
        finally:
            cur.close()


def get_admin_promo_stats() -> dict[str, Any]:
    with connection() as conn:
        if conn is None:
            return {}
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE is_active = TRUE) AS active,
                    COUNT(*) FILTER (WHERE expires_at < CURRENT_TIMESTAMP AND expires_at IS NOT NULL) AS expired,
                    COUNT(*) FILTER (WHERE max_uses IS NOT NULL) AS limited_usage,
                    COALESCE(SUM(amount), 0) AS total_amount,
                    COALESCE(SUM(amount) FILTER (WHERE current_uses > 0), 0) AS used_amount
                FROM promo_codes
                """
            )
            total, active, expired, limited_usage, total_amount, used_amount = cur.fetchone()
            return {
                "total": int(total or 0),
                "active": int(active or 0),
                "expired": int(expired or 0),
                "limited_usage": int(limited_usage or 0),
                "total_amount": total_amount or Decimal("0"),
                "used_amount": used_amount or Decimal("0"),
            }
        finally:
            cur.close()


def list_unused_promos() -> list[dict[str, Any]]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT code, COALESCE(amount, 0), COALESCE(discount, 0)
                FROM promo_codes
                WHERE COALESCE(is_used, FALSE) = FALSE
                ORDER BY code
                """
            )
            return [
                {"code": code, "amount": amount, "discount": discount}
                for code, amount, discount in cur.fetchall()
            ]
        finally:
            cur.close()


def delete_unused_promo(code: str) -> bool:
    with connection() as conn:
        if conn is None:
            return False
        cur = conn.cursor()
        try:
            cur.execute(
                "DELETE FROM promo_codes WHERE code = %s AND COALESCE(is_used, FALSE) = FALSE",
                (code,),
            )
            deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def create_promo(
    *,
    code: str,
    created_by: int,
    amount: Decimal | float | int = 0,
    discount: Decimal | float | int = 0,
    max_uses: int | None = None,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    normalized_code = (code or "").strip().upper()
    if not normalized_code:
        raise ValueError("code is required")

    amount_value = _to_decimal(amount)
    discount_value = _to_decimal(discount)
    with connection() as conn:
        if conn is None:
            raise RuntimeError("database connection failed")
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO promo_codes (
                    code, amount, discount, created_by,
                    max_uses, current_uses, expires_at,
                    is_active, is_used
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE, FALSE)
                RETURNING id, code, amount, discount, max_uses, expires_at
                """,
                (normalized_code, amount_value, discount_value, created_by, max_uses, 0, expires_at),
            )
            row = cur.fetchone()
            conn.commit()
            return {
                "id": row[0],
                "code": row[1],
                "amount": row[2],
                "discount": row[3],
                "max_uses": row[4],
                "expires_at": row[5],
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def activate_promo(user_id: int, raw_code: str) -> dict[str, Any]:
    code = (raw_code or "").strip().upper()
    if not code:
        return {"status": "empty"}

    with connection() as conn:
        if conn is None:
            return {"status": "db_unavailable"}

        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id, code, amount, COALESCE(discount, 0), is_used, used_by, used_at,
                    max_uses, current_uses, expires_at, is_active,
                    max_activations, current_activations
                FROM promo_codes
                WHERE UPPER(code) = UPPER(%s) AND COALESCE(is_active, TRUE) = TRUE
                FOR UPDATE
                """,
                (code,),
            )
            promo = cur.fetchone()
            if not promo:
                return {"status": "not_found"}

            (
                promo_id,
                stored_code,
                amount,
                discount,
                is_used,
                used_by,
                used_at,
                max_uses,
                current_uses,
                expires_at,
                is_active,
                max_activations,
                current_activations,
            ) = promo

            if expires_at and expires_at <= datetime.now(tz=expires_at.tzinfo):
                cur.execute("UPDATE promo_codes SET is_active = FALSE WHERE id = %s", (promo_id,))
                conn.commit()
                return {"status": "expired", "code": stored_code}

            amount_value = _to_decimal(amount)
            discount_value = _to_decimal(discount)
            if (not amount_value.is_finite() or not discount_value.is_finite()
                    or amount_value < 0 or not 0 <= discount_value <= 100):
                return {"status": "invalid", "code": stored_code}
            if (_limit_reached(max_uses, current_uses)
                    or _limit_reached(max_activations, current_activations)):
                return {"status": "limit_reached", "code": stored_code}
            cur.execute(
                "SELECT 1 FROM promo_code_usage WHERE user_id = %s AND promo_code_id = %s",
                (user_id, promo_id),
            )
            if cur.fetchone():
                return {"status": "already_used", "code": stored_code}
            _ensure_user(cur, user_id)

            if discount_value > 0:
                _ensure_discount_table(cur)
                cur.execute(
                    "SELECT 1 FROM user_discount_promos WHERE user_id = %s AND promo_code_id = %s FOR UPDATE",
                    (user_id, promo_id),
                )
                if cur.fetchone():
                    return {"status": "discount_already_active", "code": stored_code, "discount": discount_value}

                # A concurrent purchase can delete the active discount and record usage.
                # Recheck after waiting for that transaction's row lock.
                cur.execute(
                    "SELECT 1 FROM promo_code_usage WHERE user_id = %s AND promo_code_id = %s",
                    (user_id, promo_id),
                )
                if cur.fetchone():
                    return {"status": "already_used", "code": stored_code}
                new_current_uses = _new_current(current_uses)
                cur.execute(
                    """
                    INSERT INTO user_discount_promos (user_id, promo_code_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    RETURNING user_id
                    """,
                    (user_id, promo_id),
                )
                if not cur.fetchone():
                    return {"status": "discount_already_active", "code": stored_code}
                cur.execute(
                    """
                    UPDATE promo_codes
                    SET current_uses = %s,
                        current_activations = COALESCE(current_activations, 0) + 1,
                        used_by = %s,
                        used_at = CURRENT_TIMESTAMP,
                        is_active = CASE
                            WHEN max_uses IS NOT NULL AND %s >= max_uses THEN FALSE
                            ELSE COALESCE(is_active, TRUE)
                        END
                    WHERE id = %s
                    """,
                    (new_current_uses, user_id, new_current_uses, promo_id),
                )
                conn.commit()
                return {
                    "status": "discount_activated",
                    "code": stored_code,
                    "discount": discount_value,
                }

            if amount_value <= 0:
                return {"status": "invalid", "code": stored_code}

            next_current_activations = _new_current(current_activations)
            next_current_uses = _new_current(current_uses)
            cur.execute(
                """
                UPDATE label
                SET balance = COALESCE(balance, 0) + %s
                WHERE telegram_id = %s
                """,
                (amount_value, user_id),
            )
            cur.execute(
                """
                INSERT INTO promo_code_usage (user_id, promo_code_id)
                VALUES (%s, %s)
                """,
                (user_id, promo_id),
            )
            cur.execute(
                """
                UPDATE promo_codes
                SET current_activations = %s,
                    current_uses = %s,
                    used_by = %s,
                    used_at = CURRENT_TIMESTAMP,
                    is_used = CASE
                        WHEN (
                            (max_activations IS NOT NULL AND %s >= max_activations)
                            OR (max_uses IS NOT NULL AND %s >= max_uses)
                        )
                        THEN TRUE ELSE COALESCE(is_used, FALSE)
                    END,
                    is_active = CASE
                        WHEN (
                            (max_activations IS NOT NULL AND %s >= max_activations)
                            OR (max_uses IS NOT NULL AND %s >= max_uses)
                        )
                        THEN FALSE ELSE COALESCE(is_active, TRUE)
                    END
                WHERE id = %s
                """,
                (
                    next_current_activations,
                    next_current_uses,
                    user_id,
                    next_current_activations,
                    next_current_uses,
                    next_current_activations,
                    next_current_uses,
                    promo_id,
                ),
            )
            conn.commit()
            return {
                "status": "balance_activated",
                "code": stored_code,
                "amount": amount_value,
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.rollback()
            cur.close()
