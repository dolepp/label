"""Read-only admin user list queries."""
from __future__ import annotations

from db.pool import connection


def list_admin_user_cards() -> list[dict]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT telegram_id, tg, name
                FROM label
                WHERE telegram_id IS NOT NULL
                ORDER BY name
                """
            )
            return [
                {"telegram_id": int(row[0]), "tg": row[1], "name": row[2]}
                for row in cur.fetchall()
                if row and row[0]
            ]
        finally:
            cur.close()

