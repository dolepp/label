#!/usr/bin/env python3
"""Удаление ненужного обработчика copy_referral"""

with open("label.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Находим и комментируем обработчик copy_referral (строки 22061-22073)
start_line = 22060  # индекс 22060
end_line = 22074    # индекс 22073

found = False
for i in range(start_line, min(end_line, len(lines))):
    if "def handle_copy_referral" in lines[i] or (i > start_line and i < end_line):
        if not lines[i].startswith("#"):
            lines[i] = "# " + lines[i]
            found = True

if found:
    with open("label.py", "w", encoding="utf-8") as f:
        f.writelines(lines)
    print("✅ Обработчик handle_copy_referral закомментирован (больше не нужен)")
else:
    print("⚠️  Обработчик не найден или уже закомментирован")
