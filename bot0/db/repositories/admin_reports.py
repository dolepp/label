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

