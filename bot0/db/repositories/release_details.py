"""Read-only release detail queries."""
from __future__ import annotations

from typing import Any

from db.pool import connection


def get_album_detail(album_id: int, user_id: int | None = None) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            query = """
                SELECT release_name, release_date, status, user_id, upc_code
                FROM releases
                WHERE id = %s
            """
            params: tuple[Any, ...] = (album_id,)
            if user_id is not None:
                query += " AND user_id = %s"
                params = (album_id, user_id)
            cur.execute(query, params)
            row = cur.fetchone()
            if not row:
                return None

            cur.execute(
                """
                SELECT id, release_name, track_number
                FROM releases
                WHERE album_id = %s
                ORDER BY track_number
                """,
                (album_id,),
            )
            tracks = [
                {"id": track[0], "release_name": track[1], "track_number": track[2]}
                for track in cur.fetchall()
            ]

            return {
                "id": album_id,
                "release_name": row[0],
                "release_date": row[1],
                "status": row[2],
                "user_id": row[3],
                "upc_code": row[4],
                "tracks": tracks,
            }
        finally:
            cur.close()


def get_release_detail(release_id: int, user_id: int | None = None) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            query = """
                SELECT
                    release_type, artist_name, release_name, producer, genre,
                    release_date, performer_name, music_author, explicit_content,
                    yandex_soon, create_links, tiktok_commercial, tiktok_full_version,
                    status, upc_code, user_id, preview_start
                FROM releases
                WHERE id = %s
            """
            params: tuple[Any, ...] = (release_id,)
            if user_id is not None:
                query += " AND user_id = %s"
                params = (release_id, user_id)
            cur.execute(query, params)
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": release_id,
                "release_type": row[0],
                "artist_name": row[1],
                "release_name": row[2],
                "producer": row[3],
                "genre": row[4],
                "release_date": row[5],
                "performer_name": row[6],
                "music_author": row[7],
                "explicit_content": row[8],
                "yandex_soon": row[9],
                "create_links": row[10],
                "tiktok_commercial": row[11],
                "tiktok_full_version": row[12],
                "status": row[13],
                "upc_code": row[14],
                "user_id": row[15],
                "preview_start": row[16],
            }
        finally:
            cur.close()

