"""User queries for modular bot code."""
from __future__ import annotations

from db.pool import connection


def list_admin_ids() -> list[int]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute("SELECT telegram_id FROM label WHERE admin = 1")
            return [int(row[0]) for row in cur.fetchall() if row and row[0]]
        finally:
            cur.close()
