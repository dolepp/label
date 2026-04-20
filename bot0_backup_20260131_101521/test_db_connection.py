#!/usr/bin/env python3
"""
Скрипт для тестирования подключения к БД и пула соединений
"""
import sys
import os
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
import time

# Добавляем путь к модулям
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from config.settings import DB_CONFIG

print("=" * 60)
print("ТЕСТ ПОДКЛЮЧЕНИЯ К БАЗЕ ДАННЫХ")
print("=" * 60)

# Тест 1: Прямое подключение
print("\n1. Тестирование прямого подключения...")
try:
    conn = psycopg2.connect(
        dbname=DB_CONFIG["dbname"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        host=DB_CONFIG["host"],
        port=DB_CONFIG["port"],
        client_encoding='utf8'
    )
    cursor = conn.cursor()
    cursor.execute("SELECT version();")
    version = cursor.fetchone()
    print(f"   ✅ Подключение успешно!")
    print(f"   PostgreSQL версия: {version[0][:50]}...")
    
    cursor.execute("SELECT COUNT(*) FROM pg_stat_activity WHERE datname = %s;", (DB_CONFIG["dbname"],))
    active_connections = cursor.fetchone()[0]
    print(f"   Активных подключений к БД: {active_connections}")
    
    cursor.close()
    conn.close()
    print("   ✅ Соединение закрыто")
except Exception as e:
    print(f"   ❌ Ошибка: {e}")
    sys.exit(1)

# Тест 2: Пул соединений
print("\n2. Тестирование пула соединений...")
try:
    connection_pool = pool.ThreadedConnectionPool(
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
    print("   ✅ Пул соединений создан (min=2, max=10)")
    
    # Получаем соединение из пула
    conn = connection_pool.getconn()
    cursor = conn.cursor()
    cursor.execute("SELECT 1;")
    result = cursor.fetchone()
    cursor.close()
    
    print(f"   ✅ Соединение из пула работает: {result}")
    
    # ПРАВИЛЬНО возвращаем соединение в пул
    connection_pool.putconn(conn)
    print("   ✅ Соединение возвращено в пул")
    
    # Тест множественных подключений
    connections = []
    print("\n3. Тестирование множественных подключений (до 10)...")
    for i in range(10):
        try:
            c = connection_pool.getconn()
            connections.append(c)
            print(f"   ✅ Получено соединение {i+1}/10")
        except Exception as e:
            print(f"   ❌ Не удалось получить соединение {i+1}: {e}")
            break
    
    # Возвращаем все соединения
    print("\n4. Возврат всех соединений в пул...")
    for i, c in enumerate(connections):
        connection_pool.putconn(c)
        print(f"   ✅ Возвращено соединение {i+1}/{len(connections)}")
    
    # Проверяем, что можем снова получить соединение
    print("\n5. Проверка доступности соединений после возврата...")
    test_conn = connection_pool.getconn()
    print("   ✅ Соединение успешно получено из пула")
    connection_pool.putconn(test_conn)
    print("   ✅ Соединение возвращено в пул")
    
    # Закрываем пул
    connection_pool.closeall()
    print("\n   ✅ Пул соединений закрыт")
    
except Exception as e:
    print(f"   ❌ Ошибка пула соединений: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
print("=" * 60)

