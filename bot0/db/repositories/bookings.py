"""Studio booking queries for modular bot code."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from psycopg2 import errors

from db.pool import connection


def format_booking_date(value: date | datetime | None) -> str:
    if value is None:
        return "Дата не указана"
    return value.strftime("%d.%m.%Y")


def list_user_bookings(user_id: int, limit: int | None = 10) -> list[dict[str, Any]]:
    query = """
        SELECT id, booking_date, status
        FROM bookings
        WHERE user_id = %s
        ORDER BY booking_date DESC NULLS LAST, id DESC
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
            return [
                {"id": row[0], "booking_date": row[1], "status": row[2]}
                for row in cur.fetchall()
            ]
        except errors.UndefinedTable:
            conn.rollback()
            return []
        finally:
            cur.close()
