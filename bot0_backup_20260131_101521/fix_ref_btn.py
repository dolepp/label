#!/usr/bin/env python3
"""Исправление кнопок реферальной системы"""

with open("label.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

changes = 0

# Заменяем строку 22042 (индекс 22041)
if len(lines) > 22041:
    old = lines[22041]
    if "copy_referral" in old and "callback_data" in old:
        indent = len(old) - len(old.lstrip())
        lines[22041] = " " * indent + 'markup.add(types.InlineKeyboardButton("📤 Поделиться", url=f"https://t.me/share/url?url={referral_link}&text=Присоединяйся к TWAS Label Studio! 🎵"))\n'
        print("✅ Строка 22042 заменена")
        changes += 1

# Заменяем строку 11424 (индекс 11423)  
if len(lines) > 11423:
    old = lines[11423]
    if "copy_referral" in old and "callback_data" in old:
        new_line = old.replace('callback_data=f"copy_referral_{referral_code}"', 
                              'url=f"https://t.me/share/url?url={referral_link}&text=Присоединяйся!"')
        new_line = new_line.replace("Копировать ссылку", "Поделиться")
        lines[11423] = new_line
        print("✅ Строка 11424 заменена")
        changes += 1

if changes > 0:
    with open("label.py", "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"\n✅ Применено {changes} изменений")
else:
    print("❌ Изменения не найдены")
