"""Read-only release edit permission queries."""
from __future__ import annotations

from db.pool import connection


def get_release_edit_access(release_id: int) -> dict | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute("SELECT user_id, status FROM releases WHERE id = %s", (release_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {"id": release_id, "user_id": row[0], "status": row[1]}
        finally:
            cur.close()

