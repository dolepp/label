#!/usr/bin/env python3
import sys

print("=== ИНТЕГРАЦИЯ УЛУЧШЕННОЙ ДИСТРИБУЦИИ ===")

try:
    with open('improved_distribution.py', 'r', encoding='utf-8') as f:
        improved = f.read()
    
    with open('label.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    insert_line = None
    for i, line in enumerate(lines):
        if 'def ask_producer(message):' in line:
            insert_line = i
            break
    
    if insert_line is None:
        print("ERROR: функция ask_producer не найдена")
        sys.exit(1)
    
    print(f"OK: Найдена функция на строке {insert_line}")
    
    header = "\n# " + "="*70 + "\n"
    header += "# УЛУЧШЕННАЯ ВЕРСИЯ ДИСТРИБУЦИИ\n"
    header += "# " + "="*70 + "\n\n"
    
    new_content = lines[:insert_line] + [header, improved, "\n\n"] + lines[insert_line:]
    
    with open('label_with_improved_dist.py', 'w', encoding='utf-8') as f:
        f.writelines(new_content)
    
    print(f"OK: Файл создан ({len(new_content)} строк)")
    print("Применяю изменения...")
    
    import shutil
    shutil.copy('label.py', f'label.py.backup_improved_{sys.argv[1] if len(sys.argv) > 1 else "now"}')
    shutil.copy('label_with_improved_dist.py', 'label.py')
    
    print("OK: Изменения применены!")
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
