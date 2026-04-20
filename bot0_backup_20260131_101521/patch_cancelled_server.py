# -*- coding: utf-8 -*-
"""Патч для СЕРВЕРА: вставка проверки _support_cancelled в начало step-обработчиков."""
path = "/home/goida/label/bot0/label.py"

with open(path, "r", encoding="utf-8") as f:
    s = f.read()

# 1) process_support_input_step_response
old1 = """    user_data = ensure_user_storage(uid)
    if template_id == 'move_release' and 'support_request_data' not in user_data:"""
new1 = """    user_data = ensure_user_storage(uid)
    # Первым делом: если пользователь уже нажал «Отмена», любое следующее сообщение — только «Заявка отменена» и меню
    if user_data.pop("_support_cancelled", None):
        bot.send_message(message.chat.id, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        return
    # Если отмена уже сбросила состояние — не продолжаем, показываем главное меню
    if template_id == 'move_release' and 'support_request_data' not in user_data:"""

if old1 in s:
    s = s.replace(old1, new1, 1)
    print("1. process_support_input_step_response OK")
else:
    print("1. WARN: block not found")

# 2) process_videoshot_answer
old2 = """    user_data = ensure_user_storage(user_id)
    if 'videoshot_state' not in user_data:"""
new2 = """    user_data = ensure_user_storage(user_id)
    # Первым делом: если пользователь уже нажал «Отмена», любое следующее сообщение — только «Заявка отменена» и меню
    if user_data.pop("_support_cancelled", None):
        bot.send_message(message.chat.id, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        return
    # Если состояние уже сброшено (например, пользователь нажал «Отмена»), не продолжаем сбор
    if 'videoshot_state' not in user_data:"""

if old2 in s:
    s = s.replace(old2, new2, 1)
    print("2. process_videoshot_answer OK")
else:
    print("2. WARN: block not found")

# 3) process_support_submission
old3 = """    user_data = ensure_user_storage(message.from_user.id)
    if template_id == 'move_release' and 'support_request_data' not in user_data:"""
new3 = """    user_data = ensure_user_storage(message.from_user.id)
    # Первым делом: если пользователь уже нажал «Отмена», любое следующее сообщение — только «Заявка отменена» и меню
    if user_data.pop("_support_cancelled", None):
        bot.send_message(message.chat.id, "🚫 Заявка отменена.", reply_markup=create_main_menu())
        return
    # Если состояние сброшено отменой — не продолжаем
    if template_id == 'move_release' and 'support_request_data' not in user_data:"""

if old3 in s:
    s = s.replace(old3, new3, 1)
    print("3. process_support_submission OK")
else:
    print("3. WARN: block not found")

with open(path, "w", encoding="utf-8") as f:
    f.write(s)
print("Done.")
