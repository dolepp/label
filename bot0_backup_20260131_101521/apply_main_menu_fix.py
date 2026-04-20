#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
path = "/home/goida/label/bot0/label.py"
with open(path, "r", encoding="utf-8") as f:
    s = f.read()

# 1) Add MAIN_MENU_BUTTONS and change handler (before @bot.message_handler for main menu)
old1 = '@bot.message_handler(func=lambda message: message.text in [
    "\u0421\u043d\u043e\u0441\u044b \u041d\u0430\u0448\u0438 \u0443\u0441\u043b\u0443\u0433\u0438",
    "\u043c\u043e\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c",
'  # escaped
# Use actual chars
old1 = '@bot.message_handler(func=lambda message: message.text in [
    "' + "Сносы Наши услуги" + '",
    "' + "мой профиль" + '",
'
# Simpler: replace the opening part and add constant
if "MAIN_MENU_BUTTONS" not in s:
    s = s.replace(
        '@bot.message_handler(func=lambda message: message.text in [
    "\u0421\u043d\u043e\u0441\u044b \u041d\u0430\u0448\u0438 \u0443\u0441\u043b\u0443\u0433\u0438",',
        '# Кнопки главного меню
MAIN_MENU_BUTTONS = frozenset([
    "Сносы Наши услуги",
    "мой профиль",
    "Сносы Отзывы",
    "Помощь/вопросы",
    "Открыть приложение",
    "Статистика",
    "Поддержка",
    "О нас",
])

@bot.message_handler(func=lambda message: message.text in MAIN_MENU_BUTTONS)
@bot.message_handler(func=lambda message: message.text in [
    "Сносы Наши услуги",'
    , 1
    )
# Remove duplicate handler - we need to remove the old list and use MAIN_MENU_BUTTONS only
# Actually do step by step: first add constant before the handler block
before_handler = '@bot.message_handler(func=lambda message: message.text in ['
const_and_handler = '# Кнопки главного меню
MAIN_MENU_BUTTONS = frozenset([
    "Сносы Наши услуги", "мой профиль", "Сносы Отзывы", "Помощь/вопросы", "Открыть приложение", "Статистика", "Поддержка", "О нас",
])

@bot.message_handler(func=lambda message: message.text in MAIN_MENU_BUTTONS)'
# Find and replace: the handler line with list - replace with constant + new handler
import re
# Pattern: @bot.message_handler(func=lambda message: message.text in [ ... ])
pattern = r'@bot\.message_handler\(func=lambda message: message\.text in \[
    "Сносы Наши услуги",.*?"Открыть приложение"\s*\]\)'
if "MAIN_MENU_BUTTONS" not in s:
    s = re.sub(pattern, const_and_handler, s, count=1, flags=re.DOTALL)

with open(path, "w", encoding="utf-8") as f:
    f.write(s)
print("Step 1 done")

