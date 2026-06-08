"""Read-only admin report request queries."""
from __future__ import annotations

from collections import Counter

from db.pool import connection


def list_admin_report_requests() -> list[dict]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    rr.id,
                    rr.user_id,
                    rr.release_id,
                    rr.release_type,
                    rr.request_type,
                    rr.status,
                    rr.created_at,
                    rr.completed_at,
                    rr.report_file_id,
                    l.name,
                    l.tg,
                    r.release_name,
                    r.artist_name
                FROM report_requests rr
                JOIN label l ON rr.user_id = l.telegram_id
                LEFT JOIN releases r ON rr.release_id = r.id
                ORDER BY rr.created_at DESC
                """
            )
            reports = []
            for row in cur.fetchall():
                reports.append(
                    {
                        "id": row[0],
                        "user_id": row[1],
                        "release_id": row[2],
                        "release_type": row[3],
                        "request_type": row[4],
                        "status": row[5],
                        "created_at": row[6],
                        "completed_at": row[7],
                        "report_file_id": row[8],
                        "user_name": row[9],
                        "username": row[10],
                        "release_name": row[11],
                        "artist_name": row[12],
                    }
                )
            return reports
        finally:
            cur.close()


def count_report_statuses(reports: list[dict]) -> dict:
    counts = Counter(report.get("status") for report in reports)
    return {
        "pending": counts.get("pending", 0),
        "processing": counts.get("processing", 0),
        "completed": counts.get("completed", 0),
        "rejected": counts.get("rejected", 0),
    }



def _row_to_admin_report(row) -> dict | None:
    if not row:
        return None
    return {
        "id": row[0],
        "user_id": row[1],
        "release_id": row[2],
        "release_type": row[3],
        "request_type": row[4],
        "status": row[5],
        "created_at": row[6],
        "completed_at": row[7],
        "report_file_id": row[8],
        "user_name": row[9],
        "username": row[10],
        "release_name": row[11],
        "artist_name": row[12],
        "notes": row[13] if len(row) > 13 else None,
    }


def get_admin_report_request(report_id: int) -> dict | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    rr.id, rr.user_id, rr.release_id, rr.release_type, rr.request_type,
                    rr.status, rr.created_at, rr.completed_at, rr.report_file_id,
                    l.name, l.tg, r.release_name, r.artist_name, rr.notes
                FROM report_requests rr
                JOIN label l ON rr.user_id = l.telegram_id
                LEFT JOIN releases r ON rr.release_id = r.id
                WHERE rr.id = %s
                """,
                (report_id,),
            )
            return _row_to_admin_report(cur.fetchone())
        finally:
            cur.close()


def list_pending_report_requests() -> list[dict]:
    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT
                    rr.id, rr.user_id, rr.release_id, rr.release_type, rr.request_type,
                    rr.status, rr.created_at, rr.completed_at, rr.report_file_id,
                    l.name, l.tg, r.release_name, r.artist_name, rr.notes
                FROM report_requests rr
                JOIN label l ON rr.user_id = l.telegram_id
                LEFT JOIN releases r ON rr.release_id = r.id
                WHERE rr.status = 'pending'
                ORDER BY rr.created_at ASC
                """
            )
            return [_row_to_admin_report(row) for row in cur.fetchall()]
        finally:
            cur.close()


def mark_report_processing(report_id: int, admin_id: int | None = None) -> dict | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE report_requests
                SET status = 'processing', admin_id = COALESCE(%s, admin_id)
                WHERE id = %s
                RETURNING id
                """,
                (admin_id, report_id),
            )
            if not cur.fetchone():
                conn.rollback()
                return None
            conn.commit()
            return get_admin_report_request(report_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def reject_report_request(report_id: int, reason: str) -> dict | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE report_requests
                SET status = 'rejected',
                    completed_at = NOW(),
                    notes = %s,
                    rejection_reason = %s
                WHERE id = %s
                RETURNING id
                """,
                (reason, reason, report_id),
            )
            if not cur.fetchone():
                conn.rollback()
                return None
            conn.commit()
            return get_admin_report_request(report_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def get_report_xlsx_payload(report_id: int) -> dict | None:
    """Load all data needed to build the admin-generated XLSX report."""
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT r.user_id, r.request_type, l.name, l.tg
                FROM report_requests r
                JOIN label l ON r.user_id = l.telegram_id
                WHERE r.id = %s
                """,
                (report_id,),
            )
            report_info = cur.fetchone()
            if not report_info:
                return None
            user_id, request_type, user_name, username = report_info

            cur.execute(
                """
                SELECT telegram_id, name, tg, email, created_at, status, role
                FROM label
                WHERE telegram_id = %s
                """,
                (user_id,),
            )
            user_row = cur.fetchone()
            if not user_row:
                return {"status": "missing_user", "user_id": user_id}

            cur.execute(
                """
                SELECT id, name, type, status, created_at, updated_at, description
                FROM releases
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            releases = [
                {
                    "id": row[0],
                    "name": row[1],
                    "type": row[2],
                    "status": row[3],
                    "created_at": row[4],
                    "updated_at": row[5],
                    "description": row[6],
                    "track_count": 0,
                }
                for row in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT id, code, amount, max_uses, current_uses, expires_at, is_active
                FROM promo_codes
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            promo_codes = [
                {
                    "id": row[0],
                    "code": row[1],
                    "amount": row[2],
                    "max_uses": row[3],
                    "current_uses": row[4],
                    "expires_at": row[5],
                    "is_active": row[6],
                }
                for row in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT id, service_type, status, amount, created_at, completed_at, description
                FROM orders
                WHERE user_id = %s
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            orders = [
                {
                    "id": row[0],
                    "service_type": row[1],
                    "status": row[2],
                    "amount": row[3],
                    "created_at": row[4],
                    "completed_at": row[5],
                    "description": row[6],
                }
                for row in cur.fetchall()
            ]

            return {
                "status": "ok",
                "report": {
                    "id": report_id,
                    "user_id": user_id,
                    "request_type": request_type,
                    "user_name": user_name,
                    "username": username,
                },
                "user": {
                    "telegram_id": user_row[0],
                    "name": user_row[1],
                    "tg": user_row[2],
                    "email": user_row[3],
                    "created_at": user_row[4],
                    "status": user_row[5],
                    "role": user_row[6],
                },
                "releases": releases,
                "promo_codes": promo_codes,
                "orders": orders,
            }
        finally:
            cur.close()


def mark_report_sent(report_id: int, admin_id: int) -> bool | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                UPDATE report_requests
                SET status = 'completed',
                    completed_at = NOW(),
                    admin_id = %s
                WHERE id = %s
                """,
                (admin_id, report_id),
            )
            updated = cur.rowcount > 0
            conn.commit()
            return updated
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
