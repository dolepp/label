"""Release list queries for modular bot code."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from db.pool import connection


def format_release_date(value: date | datetime | None) -> str:
    if value is None:
        return "дата не указана"
    return value.strftime("%d.%m.%Y")


def list_user_release_cards(user_id: int, limit: int | None = None) -> list[dict[str, Any]]:
    query = """
        SELECT id, release_name, release_date, status, COALESCE(is_album, FALSE) AS is_album
        FROM releases
        WHERE user_id = %s
          AND COALESCE(is_track, FALSE) = FALSE
        ORDER BY release_date DESC NULLS LAST, id DESC
    """
    params: tuple[Any, ...] = (user_id,)
    if limit is not None:
        query += " LIMIT %s"
        params = (user_id, limit)

    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute(query, params)
            rows = cur.fetchall()
            return [
                {
                    "id": row[0],
                    "release_name": row[1],
                    "release_date": row[2],
                    "status": row[3],
                    "is_album": bool(row[4]),
                }
                for row in rows
            ]
        finally:
            cur.close()
