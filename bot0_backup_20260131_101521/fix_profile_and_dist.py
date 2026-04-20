#!/usr/bin/env python3
"""Исправление профиля (2 столбца) и дистрибуции (с навигацией)"""

with open("label.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

changes = []

# =============================================================================
# 1. ИСПРАВЛЕНИЕ ПРОФИЛЯ - заменяем одну колонку на две
# =============================================================================
# Ищем строку 12907+ где начинается show_profile
for i in range(12906, min(12950, len(lines))):
    if "markup = types.ReplyKeyboardMarkup(resize_keyboard=True)" in lines[i]:
        # Заменяем на версию с 2 столбцами
        indent = len(lines[i]) - len(lines[i].lstrip())
        lines[i] = " " * indent + "markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)\n"
        changes.append(f"✅ Строка {i+1}: Добавлен row_width=2 в show_profile")
        
        # Теперь заменяем add на add с парами кнопок
        # Найдем следующие add и сгруппируем их по 2
        j = i + 1
        buttons_found = []
        while j < len(lines) and j < i + 20:
            if 'markup.add(types.KeyboardButton(' in lines[j]:
                # Извлекаем текст кнопки
                button_text = lines[j].strip()
                buttons_found.append((j, button_text))
            elif "bot.send_message" in lines[j]:
                break
            j += 1
        
        # Группируем кнопки по 2
        if buttons_found:
            # Удаляем старые строки (комментируем)
            for btn_idx, _ in buttons_found:
                lines[btn_idx] = "# OLD: " + lines[btn_idx]
            
            # Вставляем новые кнопки после markup =
            insert_idx = i + 1
            new_lines = []
            new_lines.append(" " * indent + "markup.add(\n")
            new_lines.append(" " * indent + "    types.KeyboardButton(\"✏️ Редактировать профиль\"),\n")
            new_lines.append(" " * indent + "    types.KeyboardButton(\"📀 Мои релизы\")\n")
            new_lines.append(" " * indent + ")\n")
            new_lines.append(" " * indent + "markup.add(\n")
            new_lines.append(" " * indent + "    types.KeyboardButton(\"📊 Мои отчеты\"),\n")
            new_lines.append(" " * indent + "    types.KeyboardButton(\"🆘 Мои заявки\")\n")
            new_lines.append(" " * indent + ")\n")
            new_lines.append(" " * indent + "markup.add(\n")
            new_lines.append(" " * indent + "    types.KeyboardButton(\"🛒 Мои заказы\"),\n")
            new_lines.append(" " * indent + "    types.KeyboardButton(\"💳 Пополнить баланс\")\n")
            new_lines.append(" " * indent + ")\n")
            new_lines.append(" " * indent + "markup.add(\n")
            new_lines.append(" " * indent + "    types.KeyboardButton(\"🎟 Ввести промокод\"),\n")
            new_lines.append(" " * indent + "    types.KeyboardButton(\"👥 Пригласи друга\")\n")
            new_lines.append(" " * indent + ")\n")
            new_lines.append(" " * indent + "markup.add(types.KeyboardButton(\"◀️ Назад в меню\"))\n")
            
            # Вставляем новые строки
            for new_line in reversed(new_lines):
                lines.insert(insert_idx, new_line)
            
            changes.append(f"✅ Добавлены кнопки профиля в 2 столбца")
        
        break

# =============================================================================
# 2. ИСПРАВЛЕНИЕ ДИСТРИБУЦИИ - используем улучшенную версию
# =============================================================================
# Комментируем старый ask_release_type и указываем использовать новую систему
for i in range(4760, min(4770, len(lines))):
    if "def ask_release_type(message):" in lines[i]:
        # Добавляем комментарий о новой системе
        indent = len(lines[i]) - len(lines[i].lstrip())
        lines.insert(i, " " * indent + "# NOTE: Используйте start_distribution() для новой версии с навигацией\n")
        changes.append(f"✅ Добавлено примечание об использовании новой дистрибуции")
        break

# Ищем where "Дистрибуция" button is handled and redirect to improved version
for i in range(4690, min(4730, len(lines))):
    if "@bot.callback_query_handler" in lines[i] and "distribution" in lines[i+1]:
        # Ищем вызов ask_release_type внутри
        for j in range(i, min(i+30, len(lines))):
            if "ask_release_type" in lines[j] and "def " not in lines[j]:
                # Заменяем на start_distribution
                lines[j] = lines[j].replace("ask_release_type", "start_distribution")
                changes.append(f"✅ Строка {j+1}: Заменен вызов на start_distribution()")
                break
        break

print("\n".join(changes))

if changes:
    with open("label.py", "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"\n✅ Применено {len(changes)} изменений")
else:
    print("❌ Изменения не найдены")
