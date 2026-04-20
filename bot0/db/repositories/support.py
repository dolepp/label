"""Support request queries for modular bot code."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg2.extras import Json

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.pool import connection


ADMIN_ROLES = {"admin", "owner", "creator"}


def _row_to_request(row) -> dict[str, Any] | None:
    if row is None:
        return None
    request_id, user_id, template_id, template_title, details, request_data, status, release_id, release_name, created_at, updated_at = row
    return {
        "id": request_id,
        "user_id": user_id,
        "template_id": template_id,
        "template_title": template_title,
        "details": details or "",
        "request_data": request_data or {},
        "status": status or "принят",
        "release_id": release_id,
        "release_name": release_name,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def create_support_request(
    user_id: int,
    template_id: str,
    template_title: str,
    details: str,
    request_data: dict[str, Any] | None = None,
    release_id: int | None = None,
    release_name: str | None = None,
) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO support_requests (
                    user_id, template_id, template_title, details, request_data,
                    status, release_id, release_name, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                RETURNING id, user_id, template_id, template_title, details, request_data,
                    status, release_id, release_name, created_at, updated_at
                """,
                (
                    user_id,
                    template_id,
                    template_title,
                    details,
                    Json(request_data or {}),
                    "принят",
                    release_id,
                    release_name,
                ),
            )
            row = cur.fetchone()
            conn.commit()
            return _row_to_request(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def list_user_support_requests(user_id: int, limit: int = 10) -> list[dict[str, Any]]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id, user_id, template_id, template_title, details, request_data,
                    status, release_id, release_name, created_at, updated_at
                FROM support_requests
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            return [_row_to_request(row) for row in cur.fetchall()]
        finally:
            cur.close()


def list_recent_support_requests(limit: int = 10) -> list[dict[str, Any]]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id, user_id, template_id, template_title, details, request_data,
                    status, release_id, release_name, created_at, updated_at
                FROM support_requests
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            return [_row_to_request(row) for row in cur.fetchall()]
        finally:
            cur.close()


def get_support_request(request_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id, user_id, template_id, template_title, details, request_data,
                    status, release_id, release_name, created_at, updated_at
                FROM support_requests
                WHERE id = %s
                """,
                (request_id,),
            )
            return _row_to_request(cur.fetchone())
        finally:
            cur.close()


def update_support_status(request_id: int, status: str) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE support_requests
                SET status = %s, updated_at = NOW()
                WHERE id = %s
                RETURNING id, user_id, template_id, template_title, details, request_data,
                    status, release_id, release_name, created_at, updated_at
                """,
                (status, request_id),
            )
            row = cur.fetchone()
            conn.commit()
            return _row_to_request(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def get_support_status_counts() -> dict[str, int]:
    with connection() as conn:
        if conn is None:
            return {}
        cur = conn.cursor()
        try:
            cur.execute("SELECT status, COUNT(*) FROM support_requests GROUP BY status")
            return {status or "принят": count for status, count in cur.fetchall()}
        finally:
            cur.close()


def get_release_summary(release_id: int, user_id: int | None = None) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            if user_id is None:
                cur.execute(
                    "SELECT id, release_name, release_date, release_type, status FROM releases WHERE id = %s",
                    (release_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT id, release_name, release_date, release_type, status
                    FROM releases
                    WHERE id = %s AND user_id = %s
                    """,
                    (release_id, user_id),
                )
            row = cur.fetchone()
            if not row:
                return None
            rel_id, name, release_date, release_type, status = row
            return {
                "id": rel_id,
                "name": name,
                "date": release_date,
                "type": release_type,
                "status": status,
            }
        finally:
            cur.close()


def is_admin_user(user_id: int) -> bool:
    if user_id in set(PERMANENT_ADMINS) | set(ADMIN_IDS):
        return True

    with connection() as conn:
        if conn is None:
            return False
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT COALESCE(admin, 0), COALESCE(role, ''), COALESCE(owner, FALSE), COALESCE(creator, FALSE)
                FROM label
                WHERE telegram_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return False
            admin, role, owner, creator = row
            return bool(admin == 1 or role in ADMIN_ROLES or owner or creator)
        finally:
            cur.close()


def format_request_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if value is None:
        return "Дата не указана"
    try:
        return datetime.fromisoformat(str(value)).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(value)
