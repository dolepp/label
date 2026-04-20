"""Handlers: register on bot."""
from core.bot import bot
from handlers.common import *  # noqa: F401,F403

@bot.callback_query_handler(func=lambda call: call.data.startswith("support_template:"))
def handle_support_template_selection(call):
    template_id = call.data.split(":", 1)[1]
    template = get_support_template(template_id)

    if not template:
        bot.answer_callback_query(call.id, "Шаблон недоступен.", show_alert=True)
        return

    ensure_user_storage(call.from_user.id).pop("_support_cancelled", None)
    bot.answer_callback_query(call.id)
    prompt_support_details(call.message.chat.id, template, call.from_user.id)




@bot.callback_query_handler(func=lambda call: call.data.startswith("videoshot_select_release:"))
def handle_videoshot_release_selection(call):
    """Обработчик выбора релиза для видеошота"""
    try:
        _, template_id, release_id = call.data.split(":", 2)
        user_id = call.from_user.id
        user_data = ensure_user_storage(user_id)
        
        if 'videoshot_state' not in user_data:
            bot.answer_callback_query(call.id, "Ошибка: состояние заявки не найдено. Начните заново.", show_alert=True)
            return
        
        user_data['videoshot_state']['release_id'] = int(release_id)
        bot.answer_callback_query(call.id, "Релиз выбран")
        
        # Start asking questions
        ask_videoshot_question(call.message.chat.id, user_id, template_id, 0)
        
    except Exception as e:
        logger.error(f"Ошибка при выборе релиза для видеошота: {e}")
        bot.answer_callback_query(call.id, "Ошибка при выборе релиза.", show_alert=True)




@bot.callback_query_handler(func=lambda call: call.data.startswith("support_select_release:"))
def handle_support_release_selection(call):
    """Обработчик выбора релиза в поддержке"""
    try:
        _, template_id, release_id = call.data.split(":", 2)
        template = get_support_template(template_id)
        
        if not template:
            bot.answer_callback_query(call.id, "Шаблон не найден.", show_alert=True)
            return
        
        bot.answer_callback_query(call.id, "Релиз выбран")
        prompt_support_input(call.message.chat.id, template, int(release_id))
    except Exception as e:
        logger.error(f"Ошибка при выборе релиза: {e}")
        bot.answer_callback_query(call.id, "Ошибка при выборе релиза.", show_alert=True)




@bot.callback_query_handler(func=lambda call: call.data == "support_cancel")
def handle_support_cancel(call):
    """Обработчик отмены заявки поддержки - очищает временные данные и сбрасывает ожидание следующего сообщения"""
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    user_data = ensure_user_storage(user_id)
    _clear_support_next_step_handlers(chat_id, user_id)
    if 'support_request_data' in user_data:
        del user_data['support_request_data']
    if 'videoshot_state' in user_data:
        del user_data['videoshot_state']
    user_data['_support_cancelled'] = True
    bot.answer_callback_query(call.id, "Отменено")
    bot.send_message(chat_id, "🚫 Заявка отменена.", reply_markup=create_main_menu())




@bot.callback_query_handler(func=lambda call: call.data.startswith("design_status:"))
def handle_design_status_change(call):
    try:
        _, request_id, new_status = call.data.split(":", 2)
    except ValueError:
        bot.answer_callback_query(call.id, "Неверные данные", show_alert=True)
        return

    if new_status not in DESIGN_ORDER_STATUSES:
        bot.answer_callback_query(call.id, "Недопустимый статус", show_alert=True)
        return

    order = next((req for req in DESIGN_BRIEF_REQUESTS if req["id"] == request_id), None)
    if not order:
        bot.answer_callback_query(call.id, "Заказ не найден", show_alert=True)
        return

    order["status"] = new_status
    markup = build_design_status_markup(request_id, new_status)
    text = format_design_request_text(order)

    try:
        bot.edit_message_text(
            text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        logger.debug(f"Could not edit admin design message: {e}")

    try:
        bot.send_message(
            order["chat_id"],
            f"ℹ️ Статус вашего заказа ({DESIGN_BRIEF_TEMPLATES.get(order['service'], {}).get('title', order['service'])}) обновлён: {new_status}."
        )
    except Exception as e:
        logger.error(f"Failed to notify user about design status: {e}")

    bot.answer_callback_query(call.id, f"Статус изменён на «{new_status}»")




@bot.message_handler(commands=['support'])
@require_channel_subscription
def handle_support_command(message):
    """Обработчик команды /support - позволяет отправить любой вопрос"""
    ensure_user_storage(message.from_user.id).pop("_support_cancelled", None)
    support_text = (
        "📞 Поддержка TWAS Label Studio\n\n"
        "Напишите ваш вопрос, и мы передадим его администраторам.\n"
        "Опишите проблему максимально подробно.\n\n"
        "Для отмены отправьте /cancel"
    )
    
    msg = bot.reply_to(message, support_text, reply_markup=create_support_cancel_inline_keyboard())
    bot.register_next_step_handler(msg, process_free_support_question)




