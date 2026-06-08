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
                    status, upc_code, r.user_id, preview_start, created_at,
                    cover_file_id, audio_file_id, contract_file_id, videoshot_url, lyrics_file_id,
                    l.tg, l.name
                FROM releases r
                LEFT JOIN label l ON r.user_id = l.telegram_id
                WHERE r.id = %s
            """
            params: tuple[Any, ...] = (release_id,)
            if user_id is not None:
                query += " AND r.user_id = %s"
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
                "created_at": row[17],
                "cover_file_id": row[18],
                "audio_file_id": row[19],
                "contract_file_id": row[20],
                "videoshot_url": row[21],
                "lyrics_file_id": row[22],
                "username": row[23],
                "user_name": row[24],
            }
        finally:
            cur.close()



def get_release_detail_by_name(user_id: int, release_name: str) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id
                FROM releases
                WHERE user_id = %s AND release_name = %s
                ORDER BY created_at DESC NULLS LAST, id DESC
                LIMIT 1
                """,
                (user_id, release_name),
            )
            row = cur.fetchone()
            if not row:
                return None
            return get_release_detail(row[0], user_id=user_id)
        finally:
            cur.close()

def update_release_status(release_id: int, new_status: str) -> bool:
    with connection() as conn:
        if conn is None:
            return False
        cur = conn.cursor()
        try:
            cur.execute("SELECT is_album FROM releases WHERE id = %s", (release_id,))
            row = cur.fetchone()
            if row and row[0]:
                cur.execute(
                    "UPDATE releases SET status = %s WHERE id = %s OR album_id = %s",
                    (new_status, release_id, release_id),
                )
            else:
                cur.execute("UPDATE releases SET status = %s WHERE id = %s", (new_status, release_id))
            conn.commit()
            return cur.rowcount > 0
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def get_release_status_notification(release_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT r.release_name, r.user_id, l.telegram_id, r.platform_links, r.artist_name
                FROM releases r
                JOIN label l ON r.user_id = l.telegram_id
                WHERE r.id = %s
                """,
                (release_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "release_name": row[0],
                "user_id": row[1],
                "telegram_id": row[2],
                "platform_links": row[3],
                "artist_name": row[4],
            }
        finally:
            cur.close()


def get_release_upc(release_id: int) -> str | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute("SELECT upc_code FROM releases WHERE id = %s", (release_id,))
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            cur.close()


def update_release_upc(release_id: int, new_upc: str) -> bool:
    upc = (new_upc or "").strip()
    with connection() as conn:
        if conn is None:
            return False
        cur = conn.cursor()
        try:
            cur.execute("SELECT is_album FROM releases WHERE id = %s", (release_id,))
            row = cur.fetchone()
            if row and row[0]:
                cur.execute(
                    "UPDATE releases SET upc_code = %s WHERE id = %s OR album_id = %s",
                    (upc, release_id, release_id),
                )
            else:
                cur.execute("UPDATE releases SET upc_code = %s WHERE id = %s", (upc, release_id))
            updated = cur.rowcount > 0
            conn.commit()
            return updated
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
