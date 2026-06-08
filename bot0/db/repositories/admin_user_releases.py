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



def list_recent_releases(limit: int = 10) -> list[dict]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT r.artist_name, r.release_name, r.release_date, r.status, l.tg
                FROM releases r
                JOIN label l ON r.user_id = l.telegram_id
                ORDER BY r.release_date DESC NULLS LAST, r.id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [
                {"artist_name": row[0], "release_name": row[1], "release_date": row[2], "status": row[3], "username": row[4]}
                for row in cur.fetchall()
            ]
        finally:
            cur.close()


def list_artist_names() -> list[str]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute("SELECT DISTINCT artist_name FROM releases WHERE artist_name IS NOT NULL ORDER BY artist_name")
            return [row[0] for row in cur.fetchall() if row[0]]
        finally:
            cur.close()


def get_artist_release_stats(artist_name: str) -> dict:
    with connection() as conn:
        if conn is None:
            return {"release_count": 0, "first_release": None, "last_release": None}
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT COUNT(*) AS release_count, MIN(release_date) AS first_release, MAX(release_date) AS last_release
                FROM releases
                WHERE artist_name = %s
                """,
                (artist_name,),
            )
            row = cur.fetchone()
            return {"release_count": row[0] if row else 0, "first_release": row[1] if row else None, "last_release": row[2] if row else None}
        finally:
            cur.close()


def list_artist_releases(artist_name: str, limit: int = 10) -> list[dict]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT release_name, release_date, status
                FROM releases
                WHERE artist_name = %s
                ORDER BY release_date DESC NULLS LAST, id DESC
                LIMIT %s
                """,
                (artist_name, limit),
            )
            return [{"release_name": row[0], "release_date": row[1], "status": row[2]} for row in cur.fetchall()]
        finally:
            cur.close()
