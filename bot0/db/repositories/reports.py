"""Report request queries for modular bot code."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.pool import connection


ADMIN_ROLES = {"admin", "owner", "creator"}
ACTIVE_REPORT_STATUSES = ("pending", "processing")


def _row_to_report(row) -> dict[str, Any] | None:
    if row is None:
        return None
    report_id, user_id, release_id, release_type, request_type, status, admin_id, report_file_id, created_at, completed_at, notes = row
    return {
        "id": report_id,
        "user_id": user_id,
        "release_id": release_id,
        "release_type": release_type,
        "request_type": request_type,
        "status": status or "pending",
        "admin_id": admin_id,
        "report_file_id": report_file_id,
        "created_at": created_at,
        "completed_at": completed_at,
        "notes": notes,
    }


def format_report_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if value is None:
        return "дата не указана"
    try:
        return datetime.fromisoformat(str(value)).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return str(value)


def list_user_reports(user_id: int, limit: int = 20) -> list[dict[str, Any]]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id, user_id, release_id, release_type, request_type, status, admin_id,
                    report_file_id, created_at, completed_at, notes
                FROM report_requests
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            return [_row_to_report(row) for row in cur.fetchall()]
        finally:
            cur.close()


def get_latest_user_report(user_id: int) -> dict[str, Any] | None:
    reports = list_user_reports(user_id, limit=1)
    return reports[0] if reports else None


def get_user_report(report_id: int, user_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id, user_id, release_id, release_type, request_type, status, admin_id,
                    report_file_id, created_at, completed_at, notes
                FROM report_requests
                WHERE id = %s AND user_id = %s
                """,
                (report_id, user_id),
            )
            return _row_to_report(cur.fetchone())
        finally:
            cur.close()


def count_user_releases(user_id: int) -> int | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM releases WHERE user_id = %s", (user_id,))
            return cur.fetchone()[0]
        finally:
            cur.close()


def get_active_general_report(user_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id, user_id, release_id, release_type, request_type, status, admin_id,
                    report_file_id, created_at, completed_at, notes
                FROM report_requests
                WHERE user_id = %s
                    AND release_id IS NULL
                    AND status = ANY(%s)
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (user_id, list(ACTIVE_REPORT_STATUSES)),
            )
            return _row_to_report(cur.fetchone())
        finally:
            cur.close()


def create_general_report_request(user_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                INSERT INTO report_requests (user_id, release_type, request_type, status, created_at)
                VALUES (%s, %s, %s, %s, NOW())
                RETURNING id, user_id, release_id, release_type, request_type, status, admin_id,
                    report_file_id, created_at, completed_at, notes
                """,
                (user_id, "GENERAL", "Общий отчет по всем релизам", "pending"),
            )
            row = cur.fetchone()
            conn.commit()
            return _row_to_report(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def cancel_pending_report(report_id: int, user_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE report_requests
                SET status = 'rejected',
                    notes = COALESCE(notes || E'\n', '') || 'Отменено пользователем',
                    completed_at = NOW()
                WHERE id = %s AND user_id = %s AND status = 'pending'
                RETURNING id, user_id, release_id, release_type, request_type, status, admin_id,
                    report_file_id, created_at, completed_at, notes
                """,
                (report_id, user_id),
            )
            row = cur.fetchone()
            conn.commit()
            return _row_to_report(row)
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def get_user_identity(user_id: int) -> dict[str, Any]:
    with connection() as conn:
        if conn is None:
            return {"name": "Неизвестный пользователь", "username": "нет username"}
        cur = conn.cursor()
        try:
            cur.execute("SELECT name, tg FROM label WHERE telegram_id = %s", (user_id,))
            row = cur.fetchone()
            if not row:
                return {"name": "Неизвестный пользователь", "username": "нет username"}
            name, username = row
            return {"name": name or "Неизвестный пользователь", "username": username or "нет username"}
        finally:
            cur.close()


def list_report_admin_ids() -> list[int]:
    admin_ids = set(PERMANENT_ADMINS) | set(ADMIN_IDS)
    with connection() as conn:
        if conn is None:
            return sorted(admin_ids)
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT telegram_id
                FROM label
                WHERE telegram_id IS NOT NULL
                    AND (
                        COALESCE(admin, 0) = 1
                        OR COALESCE(role, '') = ANY(%s)
                        OR COALESCE(owner, FALSE)
                        OR COALESCE(creator, FALSE)
                    )
                """,
                (list(ADMIN_ROLES),),
            )
            admin_ids.update(row[0] for row in cur.fetchall() if row[0])
            return sorted(admin_ids)
        finally:
            cur.close()
