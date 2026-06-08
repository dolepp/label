"""Admin user role queries and mutations."""
from __future__ import annotations

from db.pool import connection


ROLE_COLUMNS = {
    "admin": "admin",
    "artist": "artist",
    "owner": "owner",
    "steezy": "steezy",
    "bibi": "bibi",
    "shvepz": "shvepz",
    "creator": "creator",
}


def get_user_roles(user_id: int) -> dict | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT name, tg, admin, artist, owner, steezy, bibi, shvepz, creator
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
                "steezy": row[5],
                "bibi": row[6],
                "shvepz": row[7],
                "creator": row[8],
            }
        finally:
            cur.close()


def toggle_user_role(user_id: int, role: str) -> dict | None:
    column = ROLE_COLUMNS.get(role)
    if column is None:
        raise ValueError(f"Unsupported role: {role}")

    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                f"SELECT {column}, name, tg FROM label WHERE telegram_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            current_value, name, tg = row
            new_value = 0 if current_value else 1
            cur.execute(
                f"UPDATE label SET {column} = %s WHERE telegram_id = %s",
                (new_value, user_id),
            )
            conn.commit()
            return {
                "telegram_id": user_id,
                "role": role,
                "value": new_value,
                "name": name,
                "tg": tg,
            }
        finally:
            cur.close()
