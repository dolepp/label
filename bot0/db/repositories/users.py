"""User queries for modular bot code."""
from __future__ import annotations

from db.pool import connection


def list_admin_ids() -> list[int]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute("SELECT telegram_id FROM label WHERE admin = 1")
            return [int(row[0]) for row in cur.fetchall() if row and row[0]]
        finally:
            cur.close()


def update_user_channel_by_username(username: str | None, channel: str) -> bool:
    normalized_username = (username or "").strip().lstrip("@")
    with connection() as conn:
        if conn is None:
            raise ConnectionError("PostgreSQL connection unavailable")
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE label SET kanal = %s WHERE tg = %s",
                (channel, normalized_username),
            )
            updated = cur.rowcount > 0
            conn.commit()
            return updated
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
