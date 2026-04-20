"""PostgreSQL connection pool for new modular code."""
import logging
import threading
from contextlib import contextmanager

from psycopg2.pool import ThreadedConnectionPool

from core.config import DB_CONFIG


logger = logging.getLogger(__name__)

_pool = None
_pool_lock = threading.Lock()


def init_pool(minconn: int = 2, maxconn: int = 10) -> bool:
    global _pool
    if _pool is not None:
        return True

    with _pool_lock:
        if _pool is not None:
            return True
        try:
            logger.info(
                "Initializing DB pool to %s:%s/%s",
                DB_CONFIG["host"],
                DB_CONFIG["port"],
                DB_CONFIG["dbname"],
            )
            _pool = ThreadedConnectionPool(
                minconn=minconn,
                maxconn=maxconn,
                dbname=DB_CONFIG["dbname"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
                host=DB_CONFIG["host"],
                port=DB_CONFIG["port"],
                client_encoding="utf8",
                connect_timeout=10,
            )
            return True
        except Exception as exc:
            logger.error("Failed to initialize DB pool: %s", exc)
            _pool = None
            return False


def get_connection():
    if _pool is None and not init_pool():
        return None
    return _pool.getconn()


def return_connection(conn) -> None:
    if conn is None:
        return
    if _pool is None:
        conn.close()
        return
    _pool.putconn(conn)


@contextmanager
def connection():
    conn = get_connection()
    try:
        yield conn
    finally:
        return_connection(conn)
