# -*- coding: utf-8 -*-
"""Работа с БД: пул соединений, подключение, возврат."""
import psycopg2
from psycopg2 import pool, Error
from psycopg2.pool import ThreadedConnectionPool
import threading
import logging
import time

from core.config import DB_CONFIG

logger = logging.getLogger(__name__)

_db_pool = None
_db_pool_lock = threading.Lock()

def init_db_pool():
    """Инициализация пула соединений PostgreSQL. Возвращает True при успехе, False при ошибке."""
    global _db_pool
    if _db_pool is not None:
        return True
    with _db_pool_lock:
        if _db_pool is not None:
            return True
        try:
            logger.info(f"Initializing DB connection pool to {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
            _db_pool = ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                dbname=DB_CONFIG["dbname"],
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
                host=DB_CONFIG["host"],
                port=DB_CONFIG["port"],
                client_encoding='utf8',
                connect_timeout=10
            )
            logger.info("✅ PostgreSQL connection pool initialized")
            return True
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ Failed to initialize connection pool: {error_msg}")
            logger.error(f"DB config: host={DB_CONFIG['host']}, port={DB_CONFIG['port']}, dbname={DB_CONFIG['dbname']}, user={DB_CONFIG['user']}")
            _db_pool = None
            return False

def get_pg_connection(max_retries=3, retry_delay=0.5):
    """Get PostgreSQL connection from pool with retry logic"""
    global _db_pool
    
    if _db_pool is None:
        init_db_pool()
    
    if _db_pool is None:
        logger.warning("Connection pool not initialized, trying direct connection")
        for attempt in range(max_retries):
            try:
                logger.debug(f"Attempting direct DB connection (attempt {attempt + 1}/{max_retries}) to {DB_CONFIG['host']}:{DB_CONFIG['port']}")
                conn = psycopg2.connect(
                    dbname=DB_CONFIG["dbname"],
                    user=DB_CONFIG["user"],
                    password=DB_CONFIG["password"],
                    host=DB_CONFIG["host"],
                    port=DB_CONFIG["port"],
                    client_encoding='utf8',
                    connect_timeout=10
                )
                logger.info("✅ Direct DB connection established")
                return conn
            except Error as e:
                error_msg = str(e)
                logger.warning(f"Direct connection attempt {attempt + 1}/{max_retries} failed: {error_msg}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                logger.error(f"❌ Failed to connect to PostgreSQL after {max_retries} attempts (direct): {error_msg}")
                logger.error(f"DB config: host={DB_CONFIG['host']}, port={DB_CONFIG['port']}, dbname={DB_CONFIG['dbname']}, user={DB_CONFIG['user']}")
                return None
    
    for attempt in range(max_retries):
        try:
            conn = _db_pool.getconn()
            return conn
        except pool.PoolError as e:
            error_msg = str(e)
            logger.warning(f"Pool error on attempt {attempt + 1}/{max_retries}: {error_msg}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
                continue
            logger.error(f"❌ Pool error after {max_retries} attempts: {error_msg}")
            try:
                logger.info("Trying direct connection as fallback...")
                conn = psycopg2.connect(
                    dbname=DB_CONFIG["dbname"],
                    user=DB_CONFIG["user"],
                    password=DB_CONFIG["password"],
                    host=DB_CONFIG["host"],
                    port=DB_CONFIG["port"],
                    client_encoding='utf8',
                    connect_timeout=10
                )
                logger.info("✅ Fallback direct connection established")
                return conn
            except Error as fallback_error:
                logger.error(f"❌ Fallback direct connection also failed: {fallback_error}")
                return None
        except Error as e:
            error_msg = str(e)
            logger.warning(f"DB error on attempt {attempt + 1}/{max_retries}: {error_msg}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay * (attempt + 1))
                continue
            logger.error(f"❌ DB error after {max_retries} attempts: {error_msg}")
            try:
                logger.info("Trying direct connection as fallback...")
                conn = psycopg2.connect(
                    dbname=DB_CONFIG["dbname"],
                    user=DB_CONFIG["user"],
                    password=DB_CONFIG["password"],
                    host=DB_CONFIG["host"],
                    port=DB_CONFIG["port"],
                    client_encoding='utf8',
                    connect_timeout=10
                )
                logger.info("✅ Fallback direct connection established")
                return conn
            except Error as fallback_error:
                logger.error(f"❌ Fallback direct connection also failed: {fallback_error}")
                return None
    
    logger.error("❌ All connection attempts failed")
    return None

def return_pg_connection(conn):
    """Возврат соединения в пул или закрытие прямого подключения"""
    global _db_pool
    if conn is None:
        return
    try:
        if _db_pool is not None:
            try:
                _db_pool.putconn(conn)
            except Exception as e:
                logger.warning(f"Could not return conn to pool (may be direct): {e}")
                try:
                    conn.close()
                except Exception:
                    pass
        else:
            conn.close()
    except Exception as e:
        logger.error(f"Error returning connection: {e}")
        try:
            conn.close()
        except Exception:
            pass
