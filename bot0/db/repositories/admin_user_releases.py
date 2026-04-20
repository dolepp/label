"""Read-only admin queries for one user's release list."""
from __future__ import annotations

from db.pool import connection


def list_admin_user_releases(user_id: int) -> dict:
    with connection() as conn:
        if conn is None:
            return {"albums": [], "singles": []}
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id, release_name, release_date, status
                FROM releases
                WHERE user_id = %s AND is_album = TRUE
                ORDER BY release_date DESC
                """,
                (user_id,),
            )
            albums = [
                {"id": row[0], "release_name": row[1], "release_date": row[2], "status": row[3]}
                for row in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT id, release_name, release_date, status
                FROM releases
                WHERE user_id = %s AND is_album = FALSE AND is_track = FALSE
                ORDER BY release_date DESC
                """,
                (user_id,),
            )
            singles = [
                {"id": row[0], "release_name": row[1], "release_date": row[2], "status": row[3]}
                for row in cur.fetchall()
            ]

            return {"albums": albums, "singles": singles}
        finally:
            cur.close()

