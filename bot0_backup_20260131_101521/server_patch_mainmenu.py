# Run on server: python3.11 server_patch_mainmenu.py
path = "/home/goida/label/bot0/label.py"
with open(path, "r", encoding="utf-8") as f:
    s = f.read()

if "MAIN_MENU_BUTTONS" not in s:
    s = s.replace(
        '@bot.message_handler(func=lambda message: message.text in [\n    "\u0421\u043d\u043e\u0441\u044b \u041d\u0430\u0448\u0438 \u0443\u0441\u043b\u0443\u0433\u0438",\n    "\u043c\u043e\u0439 \u043f\u0440\u043e\u0444\u0438\u044c",\n    # "\u0421\u043d\u043e\u0441\u044b \u041f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0434\u043e\u0433\u043e\u0432\u043e\u0440",  # \u0412\u0440\u0435\u043c\u0435\u043d\u043d\u043e \u043e\u0442\u043a\u043b\u044e\u0447\u0435\u043d\u043e\n    "\u0421\u043d\u043e\u0441\u044b \u041e\u0442\u0437\u044b\u0432\u044b",\n    "\u041f\u043e\u043c\u043e\u0449\u044c/\u0432\u043e\u043f\u0440\u043e\u0441\u044b",\n    "\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435"\n])\ndef handle_main_menu(message):',
        '# \u041a\u043d\u043e\u043f\u043a\u0438 \u0433\u043b\u0430\u0432\u043d\u043e\u0433\u043e \u043c\u0435\u043d\u044e\nMAIN_MENU_BUTTONS = frozenset([\n    "\u0421\u043d\u043e\u0441\u044b \u041d\u0430\u0448\u0438 \u0443\u0441\u043b\u0443\u0433\u0438", "\u043c\u043e\u0439 \u043f\u0440\u043e\u0444\u0438\u044c", "\u0421\u043d\u043e\u0441\u044b \u041e\u0442\u0437\u044b\u0432\u044b", "\u041f\u043e\u043c\u043e\u0449\u044c/\u0432\u043e\u043f\u0440\u043e\u0441\u044b", "\u041e\u0442\u043a\u0440\u044b\u0442\u044c \u043f\u0440\u0438\u043b\u043e\u0436\u0435\u043d\u0438\u0435",\n    "\u0421\u0442\u0430\u0442\u0438\u0441\u0442\u0438\u043a\u0430", "\u041f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0430", "\u041e \u043d\u0430\u0441",\n])\n\n@bot.message_handler(func=lambda message: message.text in MAIN_MENU_BUTTONS)\ndef handle_main_menu(message):',
        1)
    print("1 MAIN_MENU_BUTTONS ok")

s = s.replace(
    'def process_videoshot_answer(message, template_id, user_id):\n    """\u041e\u0431\u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c \u043e\u0442\u0432\u0435\u0442 \u043d\u0430 \u0432\u043e\u043f\u0440\u043e\u0441 videoshot \u0437\u0430\u044f\u0432\u043a\u0438"""\n    if is_cancel_message(message):',
    'def process_videoshot_answer(message, template_id, user_id):\n    """\u041e\u0431\u0440\u0430\u0431\u043e\u0442\u0430\u0442\u044c \u043e\u0442\u0432\u0435\u0442 \u043d\u0430 \u0432\u043e\u043f\u0440\u043e\u0441 videoshot \u0437\u0430\u044f\u0432\u043a\u0438"""\n    if message.text and message.text.strip() in MAIN_MENU_BUTTONS:\n        user_data = ensure_user_storage(user_id)\n        user_data.pop("videoshot_state", None)\n        handle_main_menu(message)\n        return\n    if is_cancel_message(message):',
    1)
print("2 ok")

s = s.replace(
    'def process_support_submission(message, template_id, release_id=None):\n    if not message.text:',
    'def process_support_submission(message, template_id, release_id=None):\n    if message.text and message.text.strip() in MAIN_MENU_BUTTONS:\n        ensure_user_storage(message.from_user.id).pop("support_request_data", None)\n        handle_main_menu(message)\n        return\n    if not message.text:',
    1)
print("3 ok")

s = s.replace(
    'def process_support_input_step_response(message, template_id, fields_to_ask, user_id=None):\n    """\u041e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0430 \u043e\u0442\u0432\u0435\u0442\u0430 \u043d\u0430 \u0432\u043e\u043f\u0440\u043e\u0441\u044b \u0448\u0430\u0431\u043b\u043e\u043d\u0430"""\n    if not message.text:',
    'def process_support_input_step_response(message, template_id, fields_to_ask, user_id=None):\n    """\u041e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0430 \u043e\u0442\u0432\u0435\u0442\u0430 \u043d\u0430 \u0432\u043e\u043f\u0440\u043e\u0441\u044b \u0448\u0430\u0431\u043b\u043e\u043d\u0430"""\n    if message.text and message.text.strip() in MAIN_MENU_BUTTONS:\n        ensure_user_storage(message.from_user.id).pop("support_request_data", None)\n        handle_main_menu(message)\n        return\n    if not message.text:',
    1)
print("4 ok")

s = s.replace(
    'def process_free_support_question(message):\n    """\u041e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0430 \u0441\u0432\u043e\u0431\u043e\u0434\u043d\u043e\u0433\u043e \u0432\u043e\u043f\u0440\u043e\u0441\u0430 \u0432 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0443"""\n    if not message.text:',
    'def process_free_support_question(message):\n    """\u041e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0430 \u0441\u0432\u043e\u0431\u043e\u0434\u043d\u043e\u0433\u043e \u0432\u043e\u043f\u0440\u043e\u0441\u0430 \u0432 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0443"""\n    if message.text and message.text.strip() in MAIN_MENU_BUTTONS:\n        handle_main_menu(message)\n        return\n    if not message.text:',
    1)
print("5 ok")

old6 = '@bot.callback_query_handler(func=lambda call: call.data == "support_cancel")\ndef handle_support_cancel(call):\n    """\u041e\u0431\u0440\u0430\u0431\u043e\u0442\u0447\u0438\u043a \u043e\u0442\u043c\u0435\u043d\u044b \u0437\u0430\u044f\u0432\u043a\u0438 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0438"""\n    user_id = call.from_user.id\n    user_data = ensure_user_storage(user_id)\n    if 'support_request_data' in user_data:\n        del user_data['support_request_data']\n    bot.answer_callback_query(call.id, "\u041e\u0442\u043c\u0435\u043d\u0435\u043d\u043e")\n    bot.send_message(call.message.chat.id, "\u0421\u0421\u0421 \u0417\u0430\u044f\u0432\u043a\u0430 \u043e\u0442\u043c\u0435\u043d\u0435\u043d\u0430.")'
new6 = '@bot.callback_query_handler(func=lambda call: call.data == "support_cancel")\ndef handle_support_cancel(call):\n    user_id = call.from_user.id\n    chat_id = call.message.chat.id\n    user_data = ensure_user_storage(user_id)\n    if 'support_request_data' in user_data: del user_data['support_request_data']\n    if 'videoshot_state' in user_data: del user_data['videoshot_state']\n    try:\n        if hasattr(bot, 'next_step_backend') and hasattr(bot.next_step_backend, 'clear_handlers'):\n            bot.next_step_backend.clear_handlers(chat_id)\n            bot.next_step_backend.clear_handlers((chat_id, user_id))\n    except Exception: pass\n    bot.answer_callback_query(call.id, "\u041e\u0442\u043c\u0435\u043d\u0435\u043d\u043e")\n    bot.send_message(chat_id, "\u0421\u0421\u0421 \u0417\u0430\u044f\u0432\u043a\u0430 \u043e\u0442\u043c\u0435\u043d\u0435\u043d\u0430.", reply_markup=create_main_menu())'
s = s.replace(old6, new6, 1)
print("6 ok")

with open(path, "w", encoding="utf-8") as f:
    f.write(s)
print("Done.")

