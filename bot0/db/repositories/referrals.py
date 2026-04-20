"""Referral queries for modular bot code."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from db.pool import connection


def _code_for_user(user_id: int) -> str:
    return f"REF{user_id}"


def ensure_referrals_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS referrals (
            id SERIAL PRIMARY KEY,
            referrer_id BIGINT NOT NULL,
            referred_id BIGINT NOT NULL UNIQUE,
            referral_code TEXT NOT NULL,
            status TEXT DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'blocked')),
            bonus_paid BOOLEAN DEFAULT FALSE,
            bonus_amount NUMERIC(10,2) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer_id ON referrals(referrer_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referred_id ON referrals(referred_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_referrals_code ON referrals(referral_code)")


def ensure_referral_columns(cur) -> None:
    cur.execute("ALTER TABLE label ADD COLUMN IF NOT EXISTS referral_code TEXT")
    cur.execute("ALTER TABLE label ADD COLUMN IF NOT EXISTS referral_count INTEGER DEFAULT 0")
    cur.execute("ALTER TABLE label ADD COLUMN IF NOT EXISTS referral_earnings NUMERIC(10,2) DEFAULT 0")


def get_or_create_referral_summary(user_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            ensure_referral_columns(cur)
            ensure_referrals_table(cur)
            cur.execute(
                """
                SELECT COALESCE(referral_code, ''), COALESCE(referral_count, 0), COALESCE(referral_earnings, 0)
                FROM label
                WHERE telegram_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                conn.commit()
                return None
            else:
                code, count, earnings = row
                if not code:
                    code = _code_for_user(user_id)
                    cur.execute("SELECT 1 FROM label WHERE referral_code = %s AND telegram_id <> %s", (code, user_id))
                    if cur.fetchone():
                        code = f"{code}X"
                    cur.execute("UPDATE label SET referral_code = %s WHERE telegram_id = %s", (code, user_id))

            cur.execute(
                """
                SELECT COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE status = 'active') AS active
                FROM referrals
                WHERE referrer_id = %s
                """,
                (user_id,),
            )
            total, active = cur.fetchone()
            conn.commit()
            return {
                "referral_code": code,
                "referral_count": int(count or 0),
                "referral_earnings": earnings or Decimal("0"),
                "total_referrals": int(total or 0),
                "active_referrals": int(active or 0),
            }
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
