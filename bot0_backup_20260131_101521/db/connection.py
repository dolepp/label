import logging
import psycopg2
from psycopg2 import Error
from config.settings import DB_CONFIG

logger = logging.getLogger(__name__)

def get_pg_connection():
    try:
        conn = psycopg2.connect(
            dbname=DB_CONFIG["dbname"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"],
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            client_encoding='utf8'
        )
        return conn
    except Error as e:
        logger.error(f"Error connecting to PostgreSQL: {e}")
        return None

