"""Admin access queries and compatibility writes."""
from __future__ import annotations

from datetime import datetime

from core.config import PERMANENT_ADMINS
from db.pool import connection


def ensure_admin_access(user_id: int, username: str | None) -> dict:
    tg = username or f"user_{user_id}"
    with connection() as conn:
        if conn is None:
            return {"allowed": False, "reason": "db_unavailable"}
        cur = conn.cursor()
        try:
            cur.execute("SELECT admin FROM label WHERE telegram_id = %s", (user_id,))
            row = cur.fetchone()

            if user_id in PERMANENT_ADMINS:
                if row is None:
                    cur.execute(
                        """
                        INSERT INTO label (tg, telegram_id, admin, artist, created_date)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (tg, user_id, 1, 1, datetime.now()),
                    )
                    conn.commit()
                elif row[0] != 1:
                    cur.execute("UPDATE label SET admin = 1 WHERE telegram_id = %s", (user_id,))
                    conn.commit()
                return {"allowed": True, "reason": "permanent_admin"}

            if row is None:
                cur.execute(
                    """
                    INSERT INTO label (tg, telegram_id, admin, artist, created_date)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (tg, user_id, 0, 0, datetime.now()),
                )
                conn.commit()
                return {"allowed": False, "reason": "not_admin"}

            return {"allowed": row[0] == 1, "reason": "db_admin" if row[0] == 1 else "not_admin"}
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
