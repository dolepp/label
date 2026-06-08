"""Broadcast recipient queries."""
from __future__ import annotations

from typing import Any

from db.pool import connection

ROLE_COLUMNS = ("artist", "admin", "owner", "steezy", "bibi", "shvepz", "creator")


def list_broadcast_recipients() -> list[dict[str, Any]]:
    """Return users with telegram ids and active role flags for broadcast filtering."""
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT telegram_id, artist, admin, owner, steezy, bibi, shvepz, creator
                FROM label
                WHERE telegram_id IS NOT NULL
                """
            )
            recipients = []
            for row in cur.fetchall():
                roles = {role: row[index + 1] for index, role in enumerate(ROLE_COLUMNS)}
                recipients.append({"telegram_id": row[0], "roles": roles})
            return recipients
        finally:
            cur.close()
