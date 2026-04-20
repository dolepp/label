#!/usr/bin/env python3
"""Скрипт для обновления функций дистрибуции"""
import re

file_path = '/home/goida/label/bot0/label.py'

try:
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Обновляем класс DistributionForm - добавляем message_id и chat_id
    old_class = r'(class DistributionForm:\s+def __init__\(self\):\s+self\.data = \{\}\s+self\.current_field = None\s+self\.fields = \[)'
    new_class = r'''class DistributionForm:
    def __init__(self):
        self.data = {}
        self.current_field = None
        self.message_id = None  # ID сообщения для редактирования
        self.chat_id = None  # ID чата
        self.fields = ['''
    
    content = re.sub(old_class, new_class, content, flags=re.MULTILINE)
    
    # Сохраняем изменения
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("✅ Класс DistributionForm обновлен")
    
except Exception as e:
    print(f"❌ Ошибка: {e}")
    import traceback
    traceback.print_exc()

