"""Release file lookup queries."""
from __future__ import annotations

from db.pool import connection


FILE_COLUMNS = {
    "contract": "contract_file_id",
    "cover": "cover_file_id",
    "audio": "audio_file_id",
}


def get_release_file_id(release_id: int, file_type: str) -> str | None:
    column_name = FILE_COLUMNS.get(file_type)
    if not column_name:
        return None

    with connection() as conn:
        if conn is None:
            raise ConnectionError("PostgreSQL connection unavailable")
        cur = conn.cursor()
        try:
            cur.execute(f"SELECT {column_name} FROM releases WHERE id = %s", (release_id,))
            row = cur.fetchone()
            return row[0] if row and row[0] else None
        finally:
            cur.close()


def get_release_attachments(release_id: int, user_id: int | None = None) -> dict | None:
    with connection() as conn:
        if conn is None:
            raise ConnectionError("PostgreSQL connection unavailable")
        cur = conn.cursor()
        try:
            query = """
                SELECT cover_file_id, audio_file_id, contract_file_id,
                    videoshot_url, lyrics_file_id, is_album, is_track, album_id, user_id
                FROM releases
                WHERE id = %s
            """
            params: tuple = (release_id,)
            if user_id is not None:
                query += " AND user_id = %s"
                params = (release_id, user_id)
            cur.execute(query, params)
            row = cur.fetchone()
            if not row:
                return None
            result = {
                "id": release_id,
                "cover_file_id": row[0],
                "audio_file_id": row[1],
                "contract_file_id": row[2],
                "videoshot_url": row[3],
                "lyrics_file_id": row[4],
                "is_album": row[5],
                "is_track": row[6],
                "album_id": row[7],
                "user_id": row[8],
                "album_cover_file_id": None,
            }
            if result["is_track"] and result["album_id"]:
                cur.execute("SELECT cover_file_id FROM releases WHERE id = %s", (result["album_id"],))
                album_row = cur.fetchone()
                result["album_cover_file_id"] = album_row[0] if album_row else None
            return result
        finally:
            cur.close()
