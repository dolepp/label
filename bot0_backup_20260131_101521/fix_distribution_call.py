#!/usr/bin/env python3
"""Замена вызова ask_release_type на start_distribution"""

with open("label.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

changes = []

# Ищем строку 3567+ где handle_distribution_agree
for i in range(3566, min(3590, len(lines))):
    if "ask_release_type(call.message)" in lines[i]:
        # Заменяем на start_distribution
        lines[i] = lines[i].replace("ask_release_type(call.message)", "start_distribution(call.message)")
        changes.append(f"✅ Строка {i+1}: Заменен вызов ask_release_type на start_distribution")
        break

if changes:
    with open("label.py", "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("\n".join(changes))
    print(f"\n✅ Применено {len(changes)} изменений")
else:
    print("❌ Изменения не найдены")
