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



def _json_links(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False)


def set_release_platform_links(release_id: int, links: dict) -> None:
    with connection() as conn:
        if conn is None:
            raise RuntimeError("database connection failed")
        cur = conn.cursor()
        try:
            cur.execute(
                "UPDATE releases SET platform_links = %s WHERE id = %s",
                (_json_links(links), release_id),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()


def add_release_platform_link(release_id: int, raw_text: str, now_label: str) -> tuple[str, str]:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Информация не может быть пустой")
    if "|" in text:
        platform, value = text.split("|", 1)
        platform_name = platform.strip() or f"Информация {now_label}"
        platform_info = value.strip()
    else:
        platform_name = f"Информация {now_label}"
        platform_info = text
    if not platform_info:
        raise ValueError("Содержание не может быть пустым")
    links = get_release_platform_links(release_id)
    links[platform_name] = platform_info
    set_release_platform_links(release_id, links)
    return platform_name, platform_info


def edit_release_platform_link(release_id: int, platform_name: str, raw_text: str) -> str:
    text = (raw_text or "").strip()
    if not text:
        raise ValueError("Информация не может быть пустой")
    links = get_release_platform_links(release_id)
    links[platform_name] = text
    set_release_platform_links(release_id, links)
    return text


def clear_release_platform_links(release_id: int) -> None:
    set_release_platform_links(release_id, {})
