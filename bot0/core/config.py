"""Application configuration loaded from environment variables."""
import os

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '..', '.env'))
    load_dotenv()
except ImportError:
    pass


BOT_TOKEN = os.environ['BOT_TOKEN']
BOT_USERNAME = os.getenv("BOT_USERNAME", "twaslabel_bot")
WEB_APP_URL = os.getenv("WEB_APP_URL", "https://twas.webhop.me")
CHANNEL_USERNAME = os.getenv("CHANNEL_USERNAME", "@twaslabel")
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "@realjustci")
MANAGER_USERNAME = os.getenv("MANAGER_USERNAME", "@twaslabelmn")
SUPPORT_HOURS = os.getenv("SUPPORT_HOURS", "10:00-22:00 МСК")

DB_CONFIG = {
    "dbname": os.environ['DB_NAME'],
    "user": os.environ['DB_USER'],
    "password": os.environ['DB_PASSWORD'],
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432"),
}

SERVICE_PRICES = {
    "cover": 500,
    "motion": 800,
    "videoshot": 1000,
    "distribution": 1299,
}

ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x.strip()]
PERMANENT_ADMINS = [int(x) for x in os.getenv('PERMANENT_ADMINS', '').split(',') if x.strip()]
