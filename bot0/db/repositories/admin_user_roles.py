"""Read-only admin user role queries."""
from __future__ import annotations

from db.pool import connection


def get_user_roles(user_id: int) -> dict | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT name, tg, admin, artist, owner, creator
                FROM label
                WHERE telegram_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "telegram_id": user_id,
                "name": row[0],
                "tg": row[1],
                "admin": row[2],
                "artist": row[3],
                "owner": row[4],
                "creator": row[5],
            }
        finally:
            cur.close()

