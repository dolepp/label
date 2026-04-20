"""Read-only admin queries for one user's report requests."""
from __future__ import annotations

from db.pool import connection


def get_user_identity(user_id: int) -> dict | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute("SELECT name, tg FROM label WHERE telegram_id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {"telegram_id": user_id, "name": row[0], "tg": row[1]}
        finally:
            cur.close()


def list_user_report_requests_for_admin(user_id: int) -> list[dict]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id, release_type, request_type, status, created_at, notes
                FROM report_requests
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            return [
                {
                    "id": row[0],
                    "release_type": row[1],
                    "request_type": row[2],
                    "status": row[3],
                    "created_at": row[4],
                    "notes": row[5],
                }
                for row in cur.fetchall()
            ]
        finally:
            cur.close()

