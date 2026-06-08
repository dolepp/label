"""Write helpers for reusable service files."""
from __future__ import annotations

from datetime import datetime

from db.pool import connection


def save_beat_contract_file(file_id: str, uploaded_by: int) -> int | None:
    """Store the current beatmaker contract file and return its row id."""
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO files (type, file_id, upload_date, uploaded_by)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                ("beat_contract", file_id, datetime.now(), uploaded_by),
            )
            row = cur.fetchone()
            conn.commit()
            return row[0] if row else None
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
