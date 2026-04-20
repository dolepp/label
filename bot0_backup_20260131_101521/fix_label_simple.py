#!/usr/bin/env python3
"""
Простое исправление label.py - заменяем только функции управления БД
Минимальные изменения для максимальной безопасности
"""
import re

def fix_label_file():
    """Исправляет критичные функции в label.py"""
    
    with open('label.py', 'r', encoding='utf-8') as f:
        content = f.read()
    
    print("Читаем label.py...")
    
    # Находим и заменяем ключевые функции
    changes_made = 0
    
    # 1. Заменяем только критичную часть - добавляем правильный возврат соединений в пул
    # Находим все места с conn.close() и заменяем на return_pg_connection(conn)
    
    # Но сначала нужно убедиться, что функция return_pg_connection правильно реализована
    # Ищем определение функции return_pg_connection
    
    return_pg_pattern = r'def return_pg_connection\(conn\):[\s\S]+?(?=\ndef |\nclass |\n@|\Z)'
    
    new_return_pg_function = '''def return_pg_connection(conn):
    """Правильный возврат соединения в пул"""
    global _db_pool
    if conn is None:
        return
    
    try:
        if _db_pool is not None:
            # Возвращаем соединение в пул
            _db_pool.putconn(conn)
        else:
            # Если пула нет, просто закрываем соединение
            conn.close()
    except Exception as e:
        logger.error(f"Error returning connection to pool: {e}")
        # Пытаемся закрыть соединение с флагом close=True
        try:
            if _db_pool is not None:
                _db_pool.putconn(conn, close=True)
            else:
                conn.close()
        except:
            pass

'''
    
    if re.search(return_pg_pattern, content):
        content = re.sub(return_pg_pattern, new_return_pg_function, content)
        changes_made += 1
        print("✅ Исправлена функция return_pg_connection")
    
    # 2. Заменяем все conn.close() на return_pg_connection(conn) ТОЛЬКО в блоках finally
    # Паттерн: finally блок с conn.close()
    
    finally_pattern = r'finally:\s+try:\s+(cur(?:sor)?\.close\(\)\s+)?conn\.close\(\)\s+except( Exception)?:\s+pass'
    finally_replacement = r'finally:\n        return_pg_connection(conn)'
    
    count = len(re.findall(finally_pattern, content))
    if count > 0:
        content = re.sub(finally_pattern, finally_replacement, content)
        changes_made += count
        print(f"✅ Заменено {count} блоков finally с conn.close() на return_pg_connection()")
    
    # 3. Также заменяем простые conn.close() в except блоках
    except_close_pattern = r'except [^:]+:\s+[^\n]*\s+conn\.close\(\)'
    
    def replace_except_close(match):
        text = match.group(0)
        return text.replace('conn.close()', 'return_pg_connection(conn)')
    
    count2 = len(re.findall(except_close_pattern, content))
    if count2 > 0:
        content = re.sub(except_close_pattern, replace_except_close, content)
        changes_made += count2
        print(f"✅ Заменено {count2} conn.close() в except блоках")
    
    # 4. Заменяем conn.close() после if conn:
    if_conn_close_pattern = r'if conn:\s+cursor\.close\(\)\s+conn\.close\(\)'
    if_conn_replacement = r'if conn:\n        return_pg_connection(conn)'
    
    count3 = len(re.findall(if_conn_close_pattern, content))
    if count3 > 0:
        content = re.sub(if_conn_close_pattern, if_conn_replacement, content)
        changes_made += count3
        print(f"✅ Заменено {count3} if conn: блоков")
    
    # Сохраняем исправленный файл
    with open('label_fixed.py', 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n📊 Всего изменений: {changes_made}")
    print(f"✅ Исправленный файл сохранен как label_fixed.py")
    
    return changes_made > 0

if __name__ == '__main__':
    print("=" * 60)
    print("ИСПРАВЛЕНИЕ ПУЛА СОЕДИНЕНИЙ В LABEL.PY")
    print("=" * 60)
    print()
    
    try:
        if fix_label_file():
            print("\n✅ Успешно исправлено!")
            print("\nСледующие шаги:")
            print("1. Проверьте label_fixed.py")
            print("2. Запустите: cp label_fixed.py label.py")
            print("3. Перезапустите бота")
        else:
            print("\n⚠️  Изменения не найдены")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

