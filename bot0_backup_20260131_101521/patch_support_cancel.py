#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
path = "/home/goida/label/bot0/label.py"
with open(path, "r", encoding="utf-8") as f:
    s = f.read()

# 1) Add create_support_cancel_inline_keyboard if missing
if "def create_support_cancel_inline_keyboard" not in s:
    old = '    return markup\n\n\ndef build_support_status_markup(request_id, active_status=None):'
    new = '    return markup\n\n\ndef create_support_cancel_inline_keyboard():\n    """\u041a\u043d\u043e\u043f\u043a\u0430 \u00ab\u041e\u0442\u043c\u0435\u043d\u0430\u00bb \u0434\u043b\u044f \u0440\u0430\u0437\u0434\u0435\u043b\u0430 \u043f\u043e\u0434\u0434\u0435\u0440\u0436\u043a\u0438."""\n    markup = types.InlineKeyboardMarkup()\n    markup.add(types.InlineKeyboardButton("\u274c \u041e\u0442\u043c\u0435\u043d\u0430", callback_data="support_cancel"))\n    return markup\n\n\ndef build_support_status_markup(request_id, active_status=None):'
    s = s.replace(old, new, 1)
    print("Added create_support_cancel_inline_keyboard")

# 2) Replace ONLY in support flow (unique context)
s = s.replace(
    'msg = bot.send_message(chat_id, "\n".join(instructions), reply_markup=create_cancel_keyboard())\n    bot.register_next_step_handler(msg, process_support_submission',
    'msg = bot.send_message(chat_id, "\n".join(instructions), reply_markup=create_support_cancel_inline_keyboard())\n    bot.register_next_step_handler(msg, process_support_submission'
)
s = s.replace(
    'msg = bot.send_message(chat_id, question_text, reply_markup=create_cancel_keyboard())\n    bot.register_next_step_handler(msg, process_videoshot_answer',
    'msg = bot.send_message(chat_id, question_text, reply_markup=create_support_cancel_inline_keyboard())\n    bot.register_next_step_handler(msg, process_videoshot_answer'
)
s = s.replace(
    'msg = bot.send_message(chat_id, "\n".join(instructions), reply_markup=create_cancel_keyboard())\n    # \u0421\u043e\u0445\u0440\u0430\u043d\u044f\u0435\u043c \u043f\u043e\u043b\u044f',
    'msg = bot.send_message(chat_id, "\n".join(instructions), reply_markup=create_support_cancel_inline_keyboard())\n    # \u0421\u043e\u0445\u0440\u0430\u044f\u0435\u043c \u043f\u043e\u043b\u044f'
)

# 3) handle_support_command
s = s.replace(
    "msg = bot.reply_to(message, support_text)\n    bot.register_next_step_handler(msg, process_free_support_question)",
    "msg = bot.reply_to(message, support_text, reply_markup=create_support_cancel_inline_keyboard())\n    bot.register_next_step_handler(msg, process_free_support_question)"
)

# 4) process_free_support_question
s = s.replace(
    'bot.reply_to(message, "\u041f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, \u043e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0442\u0435\u043a\u0441\u0442\u043e\u0432\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435.")\n        bot.register_next_step_handler(message, process_free_support_question)',
    'bot.reply_to(message, "\u041f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, \u043e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0442\u0435\u043a\u0441\u0442\u043e\u0432\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435.", reply_markup=create_support_cancel_inline_keyboard())\n        bot.register_next_step_handler(message, process_free_support_question)'
)

# 5) process_support_input_step_response
s = s.replace(
    'bot.reply_to(message, "\u041f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, \u043e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0442\u0435\u043a\u0441\u0442\u043e\u0432\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435.")\n        template = get_support_template(template_id)\n        if template:\n            prompt_support_input_step(message.chat.id, template, fields_to_ask',
    'bot.reply_to(message, "\u041f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, \u043e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0442\u0435\u043a\u0441\u0442\u043e\u0432\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435.", reply_markup=create_support_cancel_inline_keyboard())\n        template = get_support_template(template_id)\n        if template:\n            prompt_support_input_step(message.chat.id, template, fields_to_ask'
)

# 6) process_support_submission
s = s.replace(
    'bot.reply_to(message, "\u041f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, \u043e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0442\u0435\u043a\u0441\u0442\u043e\u0432\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435.")\n        template = get_support_template(template_id)\n        if template:\n            prompt_support_input(message.chat.id, template, release_id)',
    'bot.reply_to(message, "\u041f\u043e\u0436\u0430\u043b\u0443\u0439\u0441\u0442\u0430, \u043e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0442\u0435\u043a\u0441\u0442\u043e\u0432\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435.", reply_markup=create_support_cancel_inline_keyboard())\n        template = get_support_template(template_id)\n        if template:\n            prompt_support_input(message.chat.id, template, release_id)'
)

with open(path, "w", encoding="utf-8") as f:
    f.write(s)
print("Patched", path)

