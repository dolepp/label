"""Application configuration loaded from environment variables."""
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


BOT_TOKEN = os.getenv("BOT_TOKEN", "6285811276:AAHoVTSOok-_Bwxe1GWSSSsN7LiP5CynYas")
BOT_USERNAME = os.getenv("BOT_USERNAME", "twaslabel_bot")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://twas.webhop.me")
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

SERVICE_PRICES = {
    "cover": 500,
    "motion": 800,
    "videoshot": 1000,
    "distribution": 1299,
}

ADMIN_IDS = [664506846, 1429461076, 598604529, 1043989654]
PERMANENT_ADMINS = [464793425, 1398275867]
