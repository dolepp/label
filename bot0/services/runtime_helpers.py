"""Small runtime helpers used while the bot is being detached from label.py."""
from __future__ import annotations

import logging
from typing import Any

from core.config import PERMANENT_ADMINS
from db import pool as db_pool
from db.repositories.profile import get_profile
from services import admin_access, payments

logger = logging.getLogger(__name__)


def init_db_pool() -> bool:
    return db_pool.init_pool()


def get_pg_connection(max_retries: int = 3, retry_delay: float = 0.5):
    """Compatibility wrapper for legacy call sites; retry args are accepted but handled by db.pool."""
    return db_pool.get_connection()


def return_pg_connection(conn) -> None:
    db_pool.return_connection(conn)


def get_all_admins() -> list[int]:
    return admin_access.get_all_admin_ids(PERMANENT_ADMINS, get_pg_connection, return_pg_connection, logger)


def is_admin(user_id: int) -> bool:
    return admin_access.is_admin_user(user_id, PERMANENT_ADMINS, get_pg_connection, return_pg_connection, logger)


def has_access_level(user_id: int, required_levels: list[str] | tuple[str, ...]) -> bool:
    # Current access model stores admin as the effective privileged flag.
    return is_admin(user_id)


def is_profile_complete(user_id: int) -> tuple[bool, str]:
    try:
        profile = get_profile(user_id)
    except Exception as exc:
        logger.error("Failed to check profile for %s: %s", user_id, exc)
        return False, "Ошибка при проверке профиля"
    if not profile:
        return False, "Профиль не найден"
    name = profile.get("name")
    if not name or not str(name).strip():
        return False, "name"
    return True, ""


def get_user_balance_safe(user_id: int) -> float:
    return payments.get_user_balance(user_id, get_pg_connection, return_pg_connection, logger)


def change_user_balance(user_id: int, delta: float) -> bool:
    return payments.change_user_balance(user_id, delta, get_pg_connection, return_pg_connection, logger)


def is_cancel_message(message: Any) -> bool:
    if not message or not getattr(message, "text", None):
        return False
    return (message.text or "").strip().lower() in ("/cancel", "отмена", "❌ отмена")
