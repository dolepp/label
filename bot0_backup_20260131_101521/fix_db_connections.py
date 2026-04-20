#!/usr/bin/env python3
"""
Скрипт для автоматического исправления проблем с пулом соединений в label.py
Заменяет паттерны использования БД на правильные с контекстным менеджером
"""
import re
import sys

def fix_database_connections(input_file, output_file):
    """Исправляет использование БД в файле"""
    
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_lines = len(content.split('\n'))
    
    # 1. Добавляем импорт db_pool_manager в начало файла (после других импортов)
    if 'import db_pool_manager' not in content and 'from db_pool_manager import' not in content:
        # Находим место после импортов telebot
        telebot_import_pos = content.find('import telebot')
        if telebot_import_pos != -1:
            # Находим конец строки
            next_newline = content.find('\n', telebot_import_pos)
            if next_newline != -1:
                content = (content[:next_newline + 1] + 
                          'from db_pool_manager import get_db_connection, execute_query, check_connection, init_db_pool, close_db_pool\n' +
                          content[next_newline + 1:])
                print("✅ Добавлен импорт db_pool_manager")
    
    # 2. Заменяем функцию get_user_balance_safe
    old_pattern = r'def get_user_balance_safe\(user_id: int\) -> float:\s+conn = get_pg_connection\(\)[\s\S]+?finally:[\s\S]+?pass'
    new_function = '''def get_user_balance_safe(user_id: int) -> float:
    """Получить баланс пользователя с защитой от ошибок"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT COALESCE(balance, 0) FROM label WHERE telegram_id = %s', (user_id,))
                row = cur.fetchone()
                return float(row[0]) if row else 0.0
    except Exception as e:
        logger.error(f"Failed to get balance for {user_id}: {e}")
        return 0.0'''
    
    if re.search(old_pattern, content):
        content = re.sub(old_pattern, new_function, content)
        print("✅ Исправлена функция get_user_balance_safe")
    
    # 3. Заменяем функцию change_user_balance
    old_pattern = r'def change_user_balance\(user_id: int, delta: float\) -> bool:\s+conn = get_pg_connection\(\)[\s\S]+?finally:[\s\S]+?pass'
    new_function = '''def change_user_balance(user_id: int, delta: float) -> bool:
    """Изменить баланс пользователя"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE label SET balance = COALESCE(balance,0) + %s WHERE telegram_id = %s', (delta, user_id))
                conn.commit()
                return True
    except Exception as e:
        logger.error(f"Failed to change balance for {user_id} by {delta}: {e}")
        return False'''
    
    if re.search(old_pattern, content):
        content = re.sub(old_pattern, new_function, content)
        print("✅ Исправлена функция change_user_balance")
    
    # 4. Заменяем функцию is_profile_complete
    old_pattern = r'def is_profile_complete\(user_id: int\) -> tuple\[bool, str\]:[\s\S]+?"""Проверяет[\s\S]+?finally:[\s\S]+?pass'
    new_function = '''def is_profile_complete(user_id: int) -> tuple[bool, str]:
    """Проверяет, заполнен ли профиль пользователя. Возвращает (is_complete, missing_field)"""
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT name FROM label WHERE telegram_id = %s', (user_id,))
                row = cur.fetchone()
                
                if not row:
                    return (False, "Профиль не найден")
                
                name = row[0]
                if not name or not name.strip():
                    return (False, "name")
                
                return (True, "")
    except Exception as e:
        logger.error(f"Failed to check profile for {user_id}: {e}")
        return (False, "Ошибка при проверке профиля")'''
    
    if re.search(old_pattern, content):
        content = re.sub(old_pattern, new_function, content)
        print("✅ Исправлена функция is_profile_complete")
    
    # 5. Универсальная замена паттернов conn.close() и cur.close() внутри функций
    # Находим все функции, которые используют get_pg_connection() без контекстного менеджера
    
    # Паттерн: conn = get_pg_connection() ... conn.close()
    # Заменяем на: with get_db_connection() as conn:
    
    simple_pattern = r'(\s+)conn = get_pg_connection\(\)\s+if not conn:\s+return ([^\n]+)\s+try:\s+cur(?:sor)? = conn\.cursor\(\)'
    
    def replace_simple(match):
        indent = match.group(1)
        return_value = match.group(2)
        return f'{indent}try:\n{indent}    with get_db_connection() as conn:\n{indent}        cur = conn.cursor()'
    
    content = re.sub(simple_pattern, replace_simple, content)
    
    # Удаляем все cur.close() и conn.close() внутри блоков with
    content = re.sub(r'\s+cur\.close\(\)\s*\n', '\n', content)
    content = re.sub(r'\s+cursor\.close\(\)\s*\n', '\n', content)
    
    # Заменяем conn.close() на pass в finally блоках, если они после with
    content = re.sub(r'finally:\s+try:\s+cur\.close\(\)\s+conn\.close\(\)\s+except Exception:\s+pass', 
                    'except Exception as e:\n        logger.error(f"Database error: {e}")', content)
    
    # 6. Исправляем старые функции init_db_pool и get_pg_connection
    # Удаляем старую реализацию и заменяем на импорт
    old_pool_pattern = r'def init_db_pool\(\):[\s\S]+?def get_pg_connection\(max_retries=3, retry_delay=0\.5\):[\s\S]+?def return_pg_connection\(conn\):[\s\S]+?pass'
    
    if re.search(old_pool_pattern, content):
        # Просто комментируем старые функции
        content = re.sub(old_pool_pattern, 
                        '# Старые функции управления БД закомментированы - используется db_pool_manager\n# См. db_pool_manager.py', 
                        content)
        print("✅ Удалены старые функции управления БД")
    
    # Сохраняем исправленный файл
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    new_lines = len(content.split('\n'))
    
    print(f"\n📊 Статистика:")
    print(f"   Исходное количество строк: {original_lines}")
    print(f"   Новое количество строк: {new_lines}")
    print(f"   Разница: {new_lines - original_lines:+d}")
    
    return True

if __name__ == '__main__':
    input_file = 'label.py'
    output_file = 'label_fixed.py'
    
    print("=" * 60)
    print("ИСПРАВЛЕНИЕ ПРОБЛЕМ С ПУЛОМ СОЕДИНЕНИЙ")
    print("=" * 60)
    print(f"\nВходной файл: {input_file}")
    print(f"Выходной файл: {output_file}")
    print()
    
    try:
        if fix_database_connections(input_file, output_file):
            print("\n✅ Файл успешно исправлен!")
            print(f"\nПроверьте {output_file} и если все в порядке, выполните:")
            print(f"   cp {output_file} {input_file}")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

