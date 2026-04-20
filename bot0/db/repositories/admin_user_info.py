"""Read-only admin user detail queries."""
from __future__ import annotations

from decimal import Decimal

from db.pool import connection


def get_admin_user_info(user_id: int) -> dict | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            try:
                cur.execute(
                    """
                    SELECT name, tg, admin, artist, owner, creator, balance,
                           created_date, email, fio, phone
                    FROM label
                    WHERE telegram_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()
            except Exception:
                conn.rollback()
                cur.execute(
                    """
                    SELECT name, tg, admin, artist,
                           COALESCE(owner, 0),
                           COALESCE(creator, 0),
                           COALESCE(balance, 0),
                           created_date,
                           COALESCE(email, ''),
                           COALESCE(fio, '')
                    FROM label
                    WHERE telegram_id = %s
                    """,
                    (user_id,),
                )
                partial = cur.fetchone()
                row = partial + ("",) if partial else None

            if not row:
                return None

            cur.execute("SELECT COUNT(*) FROM releases WHERE user_id = %s", (user_id,))
            releases_count = cur.fetchone()[0]

            return {
                "telegram_id": user_id,
                "name": row[0],
                "tg": row[1],
                "admin": row[2],
                "artist": row[3],
                "owner": row[4],
                "creator": row[5],
                "balance": row[6] or Decimal("0"),
                "created_date": row[7],
                "email": row[8],
                "fio": row[9],
                "phone": row[10],
                "releases_count": int(releases_count or 0),
            }
        finally:
            cur.close()

