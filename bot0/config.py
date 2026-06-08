"""Legacy compatibility wrapper for configuration.

New modules should import from core.config. Existing code can continue to use
`from config import ...` until the monolith is fully migrated.
"""
from core.config import (  # noqa: F401
    ADMIN_IDS,
    BOT_TOKEN,
    BOT_USERNAME,
    CHANNEL_USERNAME,
    DB_CONFIG,
    MANAGER_USERNAME,
    OWNER_USERNAME,
    PERMANENT_ADMINS,
    SERVICE_PRICES,
    SUPPORT_HOURS,
    WEB_APP_URL,
)
