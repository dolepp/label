#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
path = "/home/goida/label/bot0/label.py"
with open(path, "r", encoding="utf-8") as f:
    s = f.read()

# 1) MAIN_MENU_BUTTONS + change handler
if "MAIN_MENU_BUTTONS" not in s:
    a = '@bot.message_handler(func=lambda message: message.text in ['
    b = '# MAIN_MENU_BUTTONS
MAIN_MENU_BUTTONS = frozenset([
    "', '", "', '", "', '", "', '", "', '", "', '", "', '", "', '",
])

@bot.message_handler(func=lambda message: message.text in MAIN_MENU_BUTTONS)
@bot.message_handler(func=lambda message: message.text in ['
    # Find the full block: from @bot.message_handler to ])
    import re
    m = re.search(r'@bot\.message_handler\(func=lambda message: message\.text in \[\n    "([^"]+)",\n    "([^"]+)",.*?"([^"]+)"\n\]\)', s)
    if m:
        s = re.sub(r'@bot\.message_handler\(func=lambda message: message\.text in \[\n    "[^"]+",\n    "[^"]+",\n    # "[^"]+",\n    "[^"]+",\n    "[^"]+",\n    "[^"]+"/\n\]\)', 'MAIN_MENU_BUTTONS = frozenset([\n    "\u0421\u043d\u043e\u0441\u044b \u041d\u0430\u0448\u0438 \u0443\u0441\u043b\u0443\u0433\u0438", "\u043c\u043e\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c", "\u0421\u043d\u043e\u0441\u044b \u041e\u0442\u0437\u044b\u0432\u044b", "\u041f\u043e\u043c\u043e\u0449\u044c/\u0432\u043e\u043f\u0440\u043e\u0441\u044b", "\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435", "\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430", "\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430", "\u041e \u043d\u0430\u0441",\n])\n\n@bot.message_handler(func=lambda message: message.text in MAIN_MENU_BUTTONS)', s, count=1)
    else:
        # Fallback: simple replace first occurrence
        s = s.replace('@bot.message_handler(func=lambda message: message.text in [', 'MAIN_MENU_BUTTONS = frozenset([\n    "\u0421\u043d\u043e\u0441\u044b \u041d\u0430\u0448\u0438 \u0443\u0441\u043b\u0443\u0433\u0438", "\u043c\u043e\u0439 \u043f\u0440\u043e\u0444\u0438\u043b\u044c", "\u0421\u043d\u043e\u0441\u044b \u041e\u0442\u0437\u044b\u0432\u044b", "\u041f\u043e\u043c\u043e\u0449\u044c/\u0432\u043e\u043f\u0440\u043e\u0441\u044b", "\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435", "\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430", "\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430", "\u041e \u043d\u0430\u0441",\n])\n\n@bot.message_handler(func=lambda message: message.text in MAIN_MENU_BUTTONS)\n@bot.message_handler(func=lambda message: message.text in [', 1)

with open(path, "w", encoding="utf-8") as f:
    f.write(s)
print("ok")

