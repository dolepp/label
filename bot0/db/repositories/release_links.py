"""Read-only release platform link queries."""
from __future__ import annotations

import json
from typing import Any

from db.pool import connection


def _parse_links(value: Any) -> dict:
    if not value or value == "{}":
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def get_release_platform_links(release_id: int) -> dict:
    with connection() as conn:
        if conn is None:
            return {}
        cur = conn.cursor()
        try:
            cur.execute("SELECT platform_links FROM releases WHERE id = %s", (release_id,))
            row = cur.fetchone()
            return _parse_links(row[0]) if row else {}
        finally:
            cur.close()


def get_release_back_callback(release_id: int) -> str:
    with connection() as conn:
        if conn is None:
            return f"my_release_detail_{release_id}_admin"
        cur = conn.cursor()
        try:
            cur.execute("SELECT is_album FROM releases WHERE id = %s", (release_id,))
            row = cur.fetchone()
            if row and row[0]:
                return f"album_detail_{release_id}_admin"
            return f"my_release_detail_{release_id}_admin"
        finally:
            cur.close()

