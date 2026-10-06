"""Review queries for the modular bot code."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from db.pool import connection


def _row_to_dict(cursor, row) -> dict[str, Any] | None:
    if row is None:
        return None
    columns = [desc[0] for desc in cursor.description]
    return dict(zip(columns, row))


def _rows_to_dicts(cursor, rows) -> list[dict[str, Any]]:
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def list_approved_reviews(category: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
    query = """
        SELECT l.name, l.tg, r.id, r.user_id, r.service_type, r.rating, r.text, r.created_date
        FROM reviews r
        JOIN label l ON r.user_id = l.telegram_id
        WHERE r.status = 'approved'
    """
    params: list[Any] = []
    if category and category != "all":
        query += " AND r.service_type = %s"
        params.append(category)
    query += " ORDER BY r.created_date DESC LIMIT %s"
    params.append(limit)

    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute(query, params)
            return _rows_to_dicts(cur, cur.fetchall())
        finally:
            cur.close()


def get_random_approved_review() -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT l.name, l.tg, r.id, r.user_id, r.service_type, r.rating, r.text, r.created_date
                FROM reviews r
                JOIN label l ON r.user_id = l.telegram_id
                WHERE r.status = %s
                ORDER BY RANDOM()
                LIMIT 1
                """,
                ("approved",),
            )
            return _row_to_dict(cur, cur.fetchone())
        finally:
            cur.close()


def get_review_detail(review_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT r.id, l.name, l.tg, r.user_id, r.service_type, r.rating, r.text, r.status, r.created_date
                FROM reviews r
                JOIN label l ON r.user_id = l.telegram_id
                WHERE r.id = %s
                """,
                (review_id,),
            )
            return _row_to_dict(cur, cur.fetchone())
        finally:
            cur.close()


def list_reviews_for_admin(pending_only: bool = True, limit: int = 20) -> list[dict[str, Any]]:
    query = """
        SELECT r.id, l.name, l.tg, r.user_id, r.service_type, r.rating, r.text, r.status, r.created_date
        FROM reviews r
        JOIN label l ON r.user_id = l.telegram_id
    """
    params: list[Any] = []
    if pending_only:
        query += " WHERE r.status = %s"
        params.append("pending")
    query += " ORDER BY r.created_date DESC LIMIT %s"
    params.append(limit)

    with connection() as conn:
        if conn is None:
            return []
        cur = conn.cursor()
        try:
            cur.execute(query, params)
            return _rows_to_dicts(cur, cur.fetchall())
        finally:
            cur.close()


def count_pending_reviews() -> int:
    with connection() as conn:
        if conn is None:
            return 0
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM reviews WHERE status = %s", ("pending",))
            return int(cur.fetchone()[0])
        finally:
            cur.close()


def create_review(user_id: int, service_type: str, rating: int, text: str) -> int | None:
    if type(rating) is not int or not 1 <= rating <= 5:
        raise ValueError("Оценка должна быть от 1 до 5")
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            # Serialize submissions by the same user across bot workers.
            cur.execute("SELECT pg_advisory_xact_lock(%s)", (user_id,))
            cur.execute(
                "SELECT 1 FROM reviews WHERE user_id = %s "
                "AND (status = 'pending' OR created_date > CURRENT_TIMESTAMP - INTERVAL '1 day') LIMIT 1",
                (user_id,),
            )
            if cur.fetchone():
                conn.rollback()
                return None
            cur.execute(
                """
                INSERT INTO reviews (user_id, service_type, rating, text, status, created_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (user_id, service_type, rating, text, "pending", datetime.now()),
            )
            review_id = cur.fetchone()[0]
            conn.commit()
            return int(review_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def approve_review(review_id: int) -> bool:
    return _set_review_status(review_id, "approved")


def _set_review_status(review_id: int, status: str) -> bool:
    with connection() as conn:
        if conn is None:
            return False
        cur = conn.cursor()
        try:
            cur.execute("UPDATE reviews SET status = %s WHERE id = %s", (status, review_id))
            updated = cur.rowcount > 0
            conn.commit()
            return updated
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def delete_review(review_id: int) -> bool:
    with connection() as conn:
        if conn is None:
            return False
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM reviews WHERE id = %s", (review_id,))
            deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
