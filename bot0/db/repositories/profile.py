"""Profile queries for modular bot code."""
from __future__ import annotations

from typing import Any

from db.pool import connection


PROFILE_FIELDS = {"name", "kanal", "fio", "email", "phone"}


def _row_to_profile(row) -> dict[str, Any] | None:
    if row is None:
        return None
    name, kanal, fio, email, phone, balance = row
    return {
        "name": name,
        "kanal": kanal,
        "fio": fio,
        "email": email,
        "phone": phone,
        "balance": balance or 0,
    }


def get_profile(user_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT name, kanal, fio, email, phone, COALESCE(balance, 0)
                FROM label
                WHERE telegram_id = %s
                """,
                (user_id,),
            )
            return _row_to_profile(cur.fetchone())
        finally:
            cur.close()


def update_profile_field(user_id: int, field: str, value: str) -> bool:
    if field not in PROFILE_FIELDS:
        raise ValueError(f"Unsupported profile field: {field}")

    with connection() as conn:
        if conn is None:
            return False
        cur = conn.cursor()
        try:
            cur.execute(f"UPDATE label SET {field} = %s WHERE telegram_id = %s", (value, user_id))
            updated = cur.rowcount > 0
            conn.commit()
            return updated
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
