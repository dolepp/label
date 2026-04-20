"""Admin access helpers for legacy compatibility code."""
from __future__ import annotations

from typing import Callable, Iterable


def get_all_admin_ids(
    permanent_admins: Iterable[int],
    get_connection: Callable,
    return_connection: Callable,
    logger,
) -> list[int]:
    admin_ids = set(permanent_admins)
    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            return sorted(admin_ids)

        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM label WHERE admin = 1")
        admin_ids.update(int(row[0]) for row in cursor.fetchall() if row and row[0])
        return sorted(admin_ids)
    except Exception as exc:
        logger.error("Error getting admins from database: %s", exc)
        return sorted(admin_ids)
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_connection(conn)


def is_admin_user(
    user_id: int,
    permanent_admins: Iterable[int],
    get_connection: Callable,
    return_connection: Callable,
    logger,
) -> bool:
    if user_id in set(permanent_admins):
        return True

    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            return False

        cursor = conn.cursor()
        cursor.execute("SELECT admin FROM label WHERE telegram_id = %s", (user_id,))
        row = cursor.fetchone()
        return bool(row and row[0] == 1)
    except Exception as exc:
        logger.error("Error checking admin status: %s", exc)
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_connection(conn)
