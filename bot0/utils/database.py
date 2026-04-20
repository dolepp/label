"""Работа с базой данных PostgreSQL: пул соединений, CRUD операции."""
import psycopg2
from psycopg2 import pool, Error
from psycopg2.pool import ThreadedConnectionPool
import threading
import logging
from contextlib import contextmanager

from core.config import DB_CONFIG

logger = logging.getLogger(__name__)

_db_pool = None
_db_pool_lock = threading.Lock()

def init_db_pool():
    global _db_pool
    with _db_pool_lock:
        if _db_pool is None:
            try:
                logger.info(f"DB pool: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
                _db_pool = ThreadedConnectionPool(
                    minconn=2, maxconn=10,
                    dbname=DB_CONFIG["dbname"],
                    user=DB_CONFIG["user"],
                    password=DB_CONFIG["password"],
                    host=DB_CONFIG["host"],
                    port=DB_CONFIG["port"]
                )
                logger.info("✅ DB pool initialized")
                return True
            except Exception as e:
                logger.error(f"❌ DB pool error: {e}")
                return False
    return True

def get_pg_connection(max_retries=3, retry_delay=0.5):
    global _db_pool
    if _db_pool is None:
        init_db_pool()
    if _db_pool is None:
        return None
    for attempt in range(max_retries):
        try:
            conn = _db_pool.getconn()
            if conn:
                return conn
        except Exception as e:
            logger.error(f"Connection error ({attempt+1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(retry_delay)
    return None

def return_pg_connection(conn):
    global _db_pool
    if conn and _db_pool:
        try:
            _db_pool.putconn(conn)
        except Exception as e:
            logger.error(f"Return connection error: {e}")

@contextmanager
def pg_connection():
    conn = get_pg_connection()
    try:
        yield conn
    finally:
        if conn:
            return_pg_connection(conn)
