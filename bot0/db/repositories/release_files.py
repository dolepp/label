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
