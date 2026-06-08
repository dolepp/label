"""Draft queries for modular bot and site-compatible distribution drafts."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from psycopg2.extras import Json

from db.pool import connection

CAMEL_TO_SNAKE = {
    "releaseType": "release_type",
    "artistName": "artist_name",
    "releaseName": "release_name",
    "releaseDate": "release_date",
    "performerName": "performer_name",
    "musicAuthor": "music_author",
    "videoshotUrl": "videoshot_url",
    "previewStart": "preview_start",
    "explicitContent": "explicit_content",
    "yandexSoon": "yandex_soon",
    "createLinks": "create_links",
    "tiktokCommercial": "tiktok_commercial",
    "tiktokFullVersion": "tiktok_full_version",
}
SNAKE_TO_CAMEL = {value: key for key, value in CAMEL_TO_SNAKE.items()}


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
                    draft_type TEXT NOT NULL,
                    data JSONB NOT NULL DEFAULT '{}'::jsonb,
                    current_step INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_drafts_user_id ON drafts(user_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_drafts_user_updated ON drafts(user_id, updated_at DESC, id DESC)")
            conn.commit()
            return True
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def parse_draft_data(data: Any) -> dict[str, Any]:
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def normalize_distribution_draft_data(data: Any) -> dict[str, Any]:
    """Return a compatibility payload with both site camelCase and bot snake_case keys."""
    result = dict(parse_draft_data(data))
    for camel, snake in CAMEL_TO_SNAKE.items():
        if camel in result and snake not in result:
            result[snake] = result[camel]
        if snake in result and camel not in result:
            result[camel] = result[snake]

    if "release_type" not in result and "releaseType" not in result:
        result["release_type"] = result["releaseType"] = "Single"

    tracks = result.get("tracks")
    if isinstance(tracks, list):
        normalized_tracks = []
        for index, track in enumerate(tracks, 1):
            if not isinstance(track, dict):
                continue
            item = dict(track)
            meta = item.get("distributionMeta") if isinstance(item.get("distributionMeta"), dict) else {}
            for key, value in meta.items():
                item.setdefault(key, value)
            item.setdefault("track_name", item.get("trackName") or item.get("release_name") or f"Трек {index}")
            item.setdefault("trackName", item.get("track_name"))
            normalized_tracks.append(item)
        result["tracks"] = normalized_tracks

    return result


def _row_to_draft(row) -> dict[str, Any] | None:
    if row is None:
        return None
    draft_id, user_id, draft_type, data, current_step, created_at, updated_at = row
    normalized_data = normalize_distribution_draft_data(data) if str(draft_type).startswith("distribution") or draft_type in {"single", "album", "release"} else parse_draft_data(data)
    return {
        "id": draft_id,
        "user_id": user_id,
        "draft_type": draft_type,
        "data": normalized_data,
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


def get_user_draft(draft_id: int, user_id: int) -> dict[str, Any] | None:
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
                WHERE id = %s AND user_id = %s
                """,
                (draft_id, user_id),
            )
            return _row_to_draft(cur.fetchone())
        finally:
            cur.close()


def save_user_draft(user_id: int, draft_type: str, data: Any, current_step: int = 0, draft_id: int | None = None) -> int | None:
    if not ensure_drafts_table():
        return None
    normalized = normalize_distribution_draft_data(data) if str(draft_type).startswith("distribution") or draft_type in {"single", "album", "release"} else parse_draft_data(data)
    with connection() as conn:
        if conn is None:
            return None
        cur = conn.cursor()
        try:
            if draft_id:
                cur.execute(
                    """
                    UPDATE drafts
                    SET draft_type = %s, data = %s, current_step = %s, updated_at = NOW()
                    WHERE id = %s AND user_id = %s
                    RETURNING id
                    """,
                    (draft_type, Json(normalized), current_step, draft_id, user_id),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO drafts (user_id, draft_type, data, current_step, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                    RETURNING id
                    """,
                    (user_id, draft_type, Json(normalized), current_step),
                )
            row = cur.fetchone()
            conn.commit()
            return row[0] if row else None
        except Exception:
            conn.rollback()
            raise
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
