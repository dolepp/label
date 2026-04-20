"""
Менеджер пула соединений PostgreSQL с автоматическим управлением ресурсами
"""
import logging
import psycopg2
from psycopg2 import pool, Error
from contextlib import contextmanager
import threading
import time
from config.settings import DB_CONFIG

logger = logging.getLogger(__name__)

# Глобальный пул соединений
_db_pool = None
_db_pool_lock = threading.Lock()

def init_db_pool():
    """Инициализация пула соединений PostgreSQL"""
    global _db_pool
    if _db_pool is None:
        with _db_pool_lock:
            if _db_pool is None:
                try:
                    _db_pool = pool.ThreadedConnectionPool(
                        minconn=2,  # Минимум соединений
                        maxconn=10,  # Максимум соединений
                        dbname=DB_CONFIG["dbname"],
                        user=DB_CONFIG["user"],
                        password=DB_CONFIG["password"],
                        host=DB_CONFIG["host"],
                        port=DB_CONFIG["port"],
                        client_encoding='utf8',
                        connect_timeout=10
                    )
                    logger.info("✅ PostgreSQL connection pool initialized (min=2, max=10)")
                    return True
                except Exception as e:
                    logger.error(f"❌ Failed to initialize connection pool: {e}")
                    _db_pool = None
                    return False
    return True

def close_db_pool():
    """Закрытие пула соединений"""
    global _db_pool
    if _db_pool is not None:
        with _db_pool_lock:
            if _db_pool is not None:
                try:
                    _db_pool.closeall()
                    logger.info("✅ PostgreSQL connection pool closed")
                except Exception as e:
                    logger.error(f"❌ Error closing connection pool: {e}")
                finally:
                    _db_pool = None

@contextmanager
def get_db_connection(max_retries=3, retry_delay=0.5):
    """
    Контекстный менеджер для получения соединения из пула.
    Автоматически возвращает соединение в пул после использования.
    
    Использование:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users")
            # ...
        # Соединение автоматически возвращается в пул
    """
    global _db_pool
    
    # Инициализируем пул при первом вызове
    if _db_pool is None:
        init_db_pool()
    
    conn = None
    is_from_pool = False
    
    try:
        if _db_pool is not None:
            # Пытаемся получить соединение из пула
            for attempt in range(max_retries):
                try:
                    conn = _db_pool.getconn()
                    is_from_pool = True
                    
                    # Проверяем, что соединение живое
                    try:
                        with conn.cursor() as test_cursor:
                            test_cursor.execute("SELECT 1")
                            test_cursor.fetchone()
                        break  # Соединение работает
                    except (Error, psycopg2.InterfaceError):
                        # Соединение мертвое, возвращаем его и берем новое
                        try:
                            _db_pool.putconn(conn, close=True)
                        except:
                            pass
                        conn = None
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay * (attempt + 1))
                            continue
                        else:
                            raise
                except pool.PoolError as e:
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))
                        continue
                    logger.error(f"Pool error getting connection: {e}")
                    raise
        
        # Если не удалось получить из пула, создаем прямое подключение
        if conn is None:
            for attempt in range(max_retries):
                try:
                    conn = psycopg2.connect(
                        dbname=DB_CONFIG["dbname"],
                        user=DB_CONFIG["user"],
                        password=DB_CONFIG["password"],
                        host=DB_CONFIG["host"],
                        port=DB_CONFIG["port"],
                        client_encoding='utf8',
                        connect_timeout=10
                    )
                    is_from_pool = False
                    break
                except Error as e:
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay * (attempt + 1))
                        continue
                    logger.error(f"Error connecting to PostgreSQL (direct): {e}")
                    raise
        
        yield conn
        
    finally:
        # Автоматически возвращаем соединение в пул или закрываем его
        if conn is not None:
            try:
                # Откатываем незафиксированные транзакции
                if not conn.closed:
                    conn.rollback()
                
                if is_from_pool and _db_pool is not None:
                    # Возвращаем соединение в пул
                    _db_pool.putconn(conn)
                else:
                    # Закрываем прямое соединение
                    conn.close()
            except Exception as e:
                logger.error(f"Error returning/closing connection: {e}")
                # Пытаемся закрыть соединение с флагом close=True
                if is_from_pool and _db_pool is not None:
                    try:
                        _db_pool.putconn(conn, close=True)
                    except:
                        pass

def execute_query(query, params=None, fetch_one=False, fetch_all=False, commit=False):
    """
    Выполнить SQL запрос с автоматическим управлением соединением.
    
    Args:
        query: SQL запрос
        params: Параметры запроса
        fetch_one: Вернуть одну строку
        fetch_all: Вернуть все строки
        commit: Зафиксировать изменения
    
    Returns:
        Результат запроса или None
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params or ())
                
                if commit:
                    conn.commit()
                
                if fetch_one:
                    return cursor.fetchone()
                elif fetch_all:
                    return cursor.fetchall()
                
                return cursor.rowcount if commit else None
    except Exception as e:
        logger.error(f"Database query error: {e}")
        logger.error(f"Query: {query}")
        logger.error(f"Params: {params}")
        return None

def check_connection():
    """Проверить доступность подключения к БД"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        logger.info("✅ Database connection OK")
        return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False

