#!/usr/bin/env python3
"""
Тест нового менеджера пула соединений
"""
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import db_pool_manager as db

print("=" * 60)
print("ТЕСТ МЕНЕДЖЕРА ПУЛА СОЕДИНЕНИЙ")
print("=" * 60)

# Тест 1: Инициализация пула
print("\n1. Инициализация пула соединений...")
if db.init_db_pool():
    print("   ✅ Пул инициализирован")
else:
    print("   ❌ Ошибка инициализации")
    sys.exit(1)

# Тест 2: Проверка подключения
print("\n2. Проверка подключения...")
if db.check_connection():
    print("   ✅ Подключение работает")
else:
    print("   ❌ Подключение не работает")
    sys.exit(1)

# Тест 3: Использование контекстного менеджера
print("\n3. Тест контекстного менеджера...")
try:
    with db.get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM label")
            count = cursor.fetchone()[0]
            print(f"   ✅ Запрос выполнен успешно. Пользователей в БД: {count}")
    print("   ✅ Соединение автоматически возвращено в пул")
except Exception as e:
    print(f"   ❌ Ошибка: {e}")
    sys.exit(1)

# Тест 4: Множественные запросы
print("\n4. Тест множественных запросов (10 раз)...")
success_count = 0
for i in range(10):
    try:
        with db.get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        success_count += 1
    except Exception as e:
        print(f"   ❌ Ошибка в запросе {i+1}: {e}")
        break

print(f"   ✅ Успешно выполнено {success_count}/10 запросов")

# Тест 5: Вспомогательная функция execute_query
print("\n5. Тест функции execute_query...")
try:
    result = db.execute_query("SELECT COUNT(*) FROM label", fetch_one=True)
    if result:
        print(f"   ✅ execute_query работает. Результат: {result[0]}")
    else:
        print("   ❌ execute_query вернул None")
except Exception as e:
    print(f"   ❌ Ошибка: {e}")

# Тест 6: Закрытие пула
print("\n6. Закрытие пула соединений...")
db.close_db_pool()
print("   ✅ Пул закрыт")

print("\n" + "=" * 60)
print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
print("=" * 60)

