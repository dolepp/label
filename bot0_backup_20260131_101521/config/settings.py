import os
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@twaslabel")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@realjustci")
MANAGER_USERNAME = os.getenv("MANAGER_USERNAME", "@twaslabelmn")
SUPPORT_HOURS = os.getenv("SUPPORT_HOURS", "10:00-22:00 МСК")
DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "60606611125"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}

