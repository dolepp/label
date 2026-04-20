#!/usr/bin/env python3
"""
Умное исправление label.py с сохранением отступов
"""
import re

def fix_label_file():
    """Исправляет критичные функции в label.py"""
    
    with open('label.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print(f"Читаем label.py ({len(lines)} строк)...")
    
    changes_made = 0
    
    # 1. Исправляем функцию return_pg_connection
    for i, line in enumerate(lines):
        if 'def return_pg_connection(conn):' in line:
            # Находим конец функции
            indent = len(line) - len(line.lstrip())
            j = i + 1
            while j < len(lines):
                if lines[j].strip() and not lines[j].startswith(' ' * (indent + 1)) and not lines[j].strip().startswith('#'):
                    break
                j += 1
            
            # Заменяем функцию
            new_function = [
                line,  # def return_pg_connection(conn):
                ' ' * (indent + 4) + '"""Правильный возврат соединения в пул"""\n',
                ' ' * (indent + 4) + 'global _db_pool\n',
                ' ' * (indent + 4) + 'if conn is None:\n',
                ' ' * (indent + 8) + 'return\n',
                ' ' * (indent + 4) + '\n',
                ' ' * (indent + 4) + 'try:\n',
                ' ' * (indent + 8) + 'if _db_pool is not None:\n',
                ' ' * (indent + 12) + '# Возвращаем соединение в пул\n',
                ' ' * (indent + 12) + '_db_pool.putconn(conn)\n',
                ' ' * (indent + 8) + 'else:\n',
                ' ' * (indent + 12) + '# Если пула нет, просто закрываем соединение\n',
                ' ' * (indent + 12) + 'conn.close()\n',
                ' ' * (indent + 4) + 'except Exception as e:\n',
                ' ' * (indent + 8) + 'logger.error(f"Error returning connection to pool: {e}")\n',
                ' ' * (indent + 8) + '# Пытаемся закрыть соединение с флагом close=True\n',
                ' ' * (indent + 8) + 'try:\n',
                ' ' * (indent + 12) + 'if _db_pool is not None:\n',
                ' ' * (indent + 16) + '_db_pool.putconn(conn, close=True)\n',
                ' ' * (indent + 12) + 'else:\n',
                ' ' * (indent + 16) + 'conn.close()\n',
                ' ' * (indent + 8) + 'except:\n',
                ' ' * (indent + 12) + 'pass\n',
                '\n'
            ]
            
            lines[i:j] = new_function
            changes_made += 1
            print("✅ Исправлена функция return_pg_connection")
            break
    
    # 2. Заменяем паттерны finally с сохранением отступов
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Ищем finally блоки
        if re.match(r'\s*finally:\s*$', line):
            indent = len(line) - len(line.lstrip())
            
            # Проверяем следующие строки
            j = i + 1
            has_conn_close = False
            has_cur_close = False
            
            # Собираем блок finally
            finally_block = []
            while j < len(lines):
                next_line = lines[j]
                next_indent = len(next_line) - len(next_line.lstrip())
                
                if next_line.strip() and next_indent <= indent:
                    break
                
                finally_block.append(next_line)
                
                if 'conn.close()' in next_line:
                    has_conn_close = True
                if 'cur.close()' in next_line or 'cursor.close()' in next_line:
                    has_cur_close = True
                
                j += 1
            
            # Если в блоке есть conn.close(), заменяем его
            if has_conn_close:
                # Заменяем весь блок finally на простой вызов return_pg_connection
                new_finally = [
                    line,  # finally:
                    ' ' * (indent + 4) + 'return_pg_connection(conn)\n'
                ]
                
                lines[i:j] = new_finally
                changes_made += 1
                i += len(new_finally)
                continue
        
        # 3. Заменяем простые if conn: ... conn.close()
        if re.match(r'\s*if conn:\s*$', line):
            indent = len(line) - len(line.lstrip())
            
            # Проверяем следующие строки
            j = i + 1
            has_conn_close = False
            
            while j < len(lines) and j < i + 5:  # Смотрим максимум 5 строк вперед
                next_line = lines[j]
                
                if 'conn.close()' in next_line:
                    has_conn_close = True
                    # Заменяем conn.close() на return_pg_connection(conn)
                    lines[j] = next_line.replace('conn.close()', 'return_pg_connection(conn)')
                    changes_made += 1
                    break
                
                next_indent = len(next_line) - len(next_line.lstrip())
                if next_line.strip() and next_indent <= indent:
                    break
                
                j += 1
        
        i += 1
    
    # Сохраняем исправленный файл
    with open('label_fixed.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"\n📊 Всего изменений: {changes_made}")
    print(f"✅ Исправленный файл сохранен как label_fixed.py")
    
    return changes_made > 0

if __name__ == '__main__':
    print("=" * 60)
    print("УМНОЕ ИСПРАВЛЕНИЕ ПУЛА СОЕДИНЕНИЙ В LABEL.PY")
    print("=" * 60)
    print()
    
    try:
        if fix_label_file():
            print("\n✅ Успешно исправлено!")
            print("\nПроверяем синтаксис...")
            
            import subprocess
            result = subprocess.run(
                ['./venv/bin/python', '-m', 'py_compile', 'label_fixed.py'],
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                print("✅ Синтаксис корректен!")
                print("\nСледующие шаги:")
                print("1. cp label_fixed.py label.py")
                print("2. Перезапустите бота")
            else:
                print(f"❌ Ошибка синтаксиса:\n{result.stderr}")
        else:
            print("\n⚠️  Изменения не найдены")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

