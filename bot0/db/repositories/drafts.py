"""Draft queries for modular bot code."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from db.pool import connection


def ensure_drafts_table() -> bool:
    with connection() as conn:
        if conn is None:
            return False
        cur = conn.cursor()
        try:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS drafts (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    draft_type VARCHAR(50) NOT NULL,
                    data TEXT NOT NULL,
                    current_step INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_drafts_user_id ON drafts(user_id)")
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def _row_to_draft(row) -> dict[str, Any] | None:
    if row is None:
        return None
    draft_id, user_id, draft_type, data, current_step, created_at, updated_at = row
    return {
        "id": draft_id,
        "user_id": user_id,
        "draft_type": draft_type,
        "data": data,
        "current_step": current_step or 0,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def list_user_drafts(user_id: int, limit: int = 10) -> list[dict[str, Any]] | None:
    if not ensure_drafts_table():
        return None

    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute(
                """
                SELECT id, user_id, draft_type, data, current_step, created_at, updated_at
                FROM drafts
                WHERE user_id = %s
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            return [_row_to_draft(row) for row in cur.fetchall()]
        finally:
            cur.close()


def count_user_drafts(user_id: int) -> int | None:
    if not ensure_drafts_table():
        return None

    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute("SELECT COUNT(*) FROM drafts WHERE user_id = %s", (user_id,))
            return cur.fetchone()[0]
        finally:
            cur.close()


def delete_user_draft(draft_id: int, user_id: int) -> bool | None:
    if not ensure_drafts_table():
        return None

    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM drafts WHERE id = %s AND user_id = %s", (draft_id, user_id))
            deleted = cur.rowcount > 0
            conn.commit()
            return deleted
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def format_draft_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    if value is None:
        return "Дата не указана"
    try:
        return datetime.fromisoformat(str(value)).strftime("%d.%m.%Y")
    except Exception:
        return str(value)
