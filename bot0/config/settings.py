"""Deprecated settings wrapper.

This directory conflicts with the legacy `config.py` module name. Import from
core.config in new code.
"""
from core.config import (  # noqa: F401
    CHANNEL_USERNAME,
    DB_CONFIG,
    MANAGER_USERNAME,
    OWNER_USERNAME,
    SUPPORT_HOURS,
)
