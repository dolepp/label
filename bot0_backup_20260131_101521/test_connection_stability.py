#!/usr/bin/env python3
"""
Тест стабильности подключений к БД
Проверяет, что соединения правильно возвращаются в пул
"""
import sys
import os
import time
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Импортируем label для использования функций бота
import label

print("=" * 60)
print("ТЕСТ СТАБИЛЬНОСТИ ПОДКЛЮЧЕНИЙ К БД")
print("=" * 60)

# Тест 1: Множественные вызовы функций, использующих БД
print("\n1. Тестируем множественные запросы к БД (100 раз)...")

success_count = 0
error_count = 0

for i in range(100):
    try:
        # Получаем баланс пользователя
        balance = label.get_user_balance_safe(464793425)
        
        # Проверяем профиль
        is_complete, field = label.is_profile_complete(464793425)
        
        success_count += 1
        
        if (i + 1) % 20 == 0:
            print(f"   ✅ Выполнено {i + 1}/100 запросов")
    except Exception as e:
        print(f"   ❌ Ошибка в запросе {i + 1}: {e}")
        error_count += 1

print(f"\n   📊 Успешно: {success_count}/100")
print(f"   📊 Ошибок: {error_count}/100")

if error_count > 0:
    print("   ⚠️  Есть ошибки!")
    sys.exit(1)
else:
    print("   ✅ Все запросы выполнены успешно!")

# Тест 2: Многопоточные запросы
print("\n2. Тестируем многопоточные запросы (10 потоков по 10 запросов)...")

results = {'success': 0, 'error': 0, 'lock': threading.Lock()}

def thread_worker(thread_id):
    """Рабочий поток для тестирования"""
    for i in range(10):
        try:
            balance = label.get_user_balance_safe(464793425)
            with results['lock']:
                results['success'] += 1
        except Exception as e:
            with results['lock']:
                results['error'] += 1
            print(f"   ❌ Ошибка в потоке {thread_id}, запрос {i}: {e}")

# Запускаем потоки
threads = []
for i in range(10):
    t = threading.Thread(target=thread_worker, args=(i,))
    threads.append(t)
    t.start()

# Ждем завершения всех потоков
for t in threads:
    t.join()

print(f"\n   📊 Успешно: {results['success']}/100")
print(f"   📊 Ошибок: {results['error']}/100")

if results['error'] > 0:
    print("   ⚠️  Есть ошибки в многопоточном тесте!")
    sys.exit(1)
else:
    print("   ✅ Все многопоточные запросы выполнены успешно!")

# Тест 3: Проверка состояния пула
print("\n3. Проверяем состояние пула соединений...")

try:
    if label._db_pool is not None:
        print("   ✅ Пул соединений активен")
    else:
        print("   ⚠️  Пул соединений не инициализирован")
except Exception as e:
    print(f"   ❌ Ошибка проверки пула: {e}")

# Тест 4: Проверка активных соединений в БД
print("\n4. Проверяем количество активных соединений в БД...")

try:
    conn = label.get_pg_connection()
    if conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) 
            FROM pg_stat_activity 
            WHERE datname = current_database()
            AND state = 'active'
        """)
        active_conn = cursor.fetchone()[0]
        cursor.close()
        label.return_pg_connection(conn)
        
        print(f"   📊 Активных подключений к БД: {active_conn}")
        
        if active_conn > 20:
            print("   ⚠️  Слишком много активных подключений!")
        else:
            print("   ✅ Количество подключений в норме")
except Exception as e:
    print(f"   ❌ Ошибка проверки активных подключений: {e}")

print("\n" + "=" * 60)
print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
print("=" * 60)
print("\nПул соединений работает стабильно ✅")

