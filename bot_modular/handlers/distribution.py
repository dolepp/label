"""Handlers: register on bot."""
from core.bot import bot
from handlers.common import *  # noqa: F401,F403

@bot.callback_query_handler(func=lambda call: call.data.startswith("distribution_pay_"))
def handle_distribution_pay(call):
    """Create payment for distribution based on calculated cost"""
    try:
        amount = int(call.data.split("_")[2])
    except Exception:
        bot.answer_callback_query(call.id, "❌ Неверная сумма", show_alert=True)
        return

    user_id = call.from_user.id
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT COALESCE(balance, 0) FROM label WHERE telegram_id = %s', (user_id,))
        row = cursor.fetchone()
        current_balance = float(row[0]) if row else 0.0

        if current_balance >= amount:
            # Списать и сохранить релиз
            cursor.execute('UPDATE label SET balance = COALESCE(balance,0) - %s WHERE telegram_id = %s',
                           (amount, user_id))
            conn.commit()

            try:
                bot.edit_message_text(
                    f"✅ Списано {amount}₽ с баланса. Отправляем релиз на модерацию...",
                    call.message.chat.id,
                    call.message.message_id
                )
            except Exception:
                bot.send_message(call.message.chat.id, f"✅ Списано {amount}₽ с баланса. Отправляем релиз...")

            # Сохранить релиз для пользователя
            save_release_data_for_user(user_id, call.message.chat.id)
        else:
            needed = int(amount - current_balance)
            markup = types.InlineKeyboardMarkup()
            # Сохраняем ожидаемую операцию, чтобы после пополнения продолжить автоматически и не терять прогресс
            bot.user_data.setdefault(user_id, {})['pending_operation'] = {
                'type': 'distribution',
                'amount': amount,
                'needed': needed,
                'resume': True
            }
            markup.add(
                types.InlineKeyboardButton(f"Пополнить на {needed}₽", callback_data=f"topup_pay_{needed}"),
                types.InlineKeyboardButton("Повторить оплату", callback_data=f"distribution_pay_{amount}")
            )
            bot.edit_message_text(
                f"❌ Недостаточно средств. Требуется {amount}₽, на балансе {current_balance:,.2f}₽.\n\nПополните баланс и попробуйте снова.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
    except Exception as e:
        logger.error(f"Error in handle_distribution_pay: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка обработки оплаты", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.message_handler(commands=['cancel'])
def cancel_distribution(message):
    """Отмена процесса создания релиза"""
    user_id = message.from_user.id
    if user_id in bot.user_data:
        # Очищаем только контекст создания релиза, оставляя возможные pending операции
        for key in list(bot.user_data[user_id].keys()):
            if key not in ('pending_operation',):
                bot.user_data[user_id].pop(key, None)
    bot.send_message(message.chat.id, "❌ Процесс создания релиза отменён.", reply_markup=create_main_menu())




@bot.callback_query_handler(func=lambda call: call.data == "distribution_agree")
def handle_distribution_agree(call):
    """Handle agreement with distribution terms"""
    conn = None
    try:
        conn = get_pg_connection()
        if not conn:
            bot.answer_callback_query(call.id, "Ошибка подключения к базе данных", show_alert=True)
            return

        with conn.cursor() as cursor:
            cursor.execute(
                'INSERT INTO distribution_agreements (user_id, agreed) VALUES (%s, %s)',
                (call.from_user.id, True)
            )
            conn.commit()

        ask_release_type(call.message)
    except Exception as e:
        logger.error(f"Error saving distribution agreement: {e}")
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data == "service_distribution")
def handle_distribution_service(call):
    """Handle distribution service selection"""
    user_id = call.from_user.id
    
    # Проверяем заполненность профиля перед началом дистрибуции
    is_complete, missing_field = is_profile_complete(user_id)
    if not is_complete:
        if missing_field == "name":
            bot.answer_callback_query(
                call.id,
                "❌ Перед отгрузкой необходимо заполнить профиль. Укажите ник артиста в разделе 'Профиль' → 'Редактировать профиль'",
                show_alert=True
            )
            return
        else:
            bot.answer_callback_query(
                call.id,
                f"❌ Ошибка: {missing_field}",
                show_alert=True
            )
            return
    
    show_distribution_agreement(call.message)




@bot.callback_query_handler(func=lambda call: call.data == "distribution_disagree")
def handle_distribution_disagree(call):
    """Handle disagreement with distribution terms"""
    bot.edit_message_text(
        "Для использования услуги дистрибуции необходимо согласие со всеми условиями. "
        "Если у вас есть вопросы, обратитесь в поддержку.",
        call.message.chat.id,
        call.message.message_id
    )




@bot.callback_query_handler(func=lambda call: call.data.startswith("distribution_pay_"))
def handle_distribution_pay(call):
    """Create payment for distribution based on calculated cost"""
    try:
        amount = int(call.data.split("_")[2])
    except Exception:
        bot.answer_callback_query(call.id, "❌ Неверная сумма", show_alert=True)
        return

    user_id = call.from_user.id
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT COALESCE(balance, 0) FROM label WHERE telegram_id = %s', (user_id,))
        row = cursor.fetchone()
        current_balance = float(row[0]) if row else 0.0

        if current_balance >= amount:
            # Списать и сохранить релиз
            cursor.execute('UPDATE label SET balance = COALESCE(balance,0) - %s WHERE telegram_id = %s',
                           (amount, user_id))
            conn.commit()

            try:
                bot.edit_message_text(
                    f"✅ Списано {amount}₽ с баланса. Отправляем релиз на модерацию...",
                    call.message.chat.id,
                    call.message.message_id
                )
            except Exception:
                bot.send_message(call.message.chat.id, f"✅ Списано {amount}₽ с баланса. Отправляем релиз...")

            # Сохранить релиз для пользователя
            save_release_data_for_user(user_id, call.message.chat.id)
        else:
            needed = int(amount - current_balance)
            markup = types.InlineKeyboardMarkup()
            # Сохраняем ожидаемую операцию, чтобы после пополнения продолжить автоматически и не терять прогресс
            bot.user_data.setdefault(user_id, {})['pending_operation'] = {
                'type': 'distribution',
                'amount': amount,
                'needed': needed,
                'resume': True
            }
            markup.add(
                types.InlineKeyboardButton(f"Пополнить на {needed}₽", callback_data=f"topup_pay_{needed}"),
                types.InlineKeyboardButton("Повторить оплату", callback_data=f"distribution_pay_{amount}")
            )
            bot.edit_message_text(
                f"❌ Недостаточно средств. Требуется {amount}₽, на балансе {current_balance:,.2f}₽.\n\nПополните баланс и попробуйте снова.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
    except Exception as e:
        logger.error(f"Error in handle_distribution_pay: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка обработки оплаты", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.message_handler(commands=['cancel'])
def cancel_distribution(message):
    """Отмена процесса создания релиза"""
    user_id = message.from_user.id
    if user_id in bot.user_data:
        # Очищаем только контекст создания релиза, оставляя возможные pending операции
        for key in list(bot.user_data[user_id].keys()):
            if key not in ('pending_operation',):
                bot.user_data[user_id].pop(key, None)
    bot.send_message(message.chat.id, "❌ Процесс создания релиза отменён.", reply_markup=create_main_menu())




@bot.callback_query_handler(func=lambda call: call.data == "distribution_agree")
def handle_distribution_agree(call):
    """Handle agreement with distribution terms"""
    conn = None
    try:
        conn = get_pg_connection()
        if not conn:
            bot.answer_callback_query(call.id, "Ошибка подключения к базе данных", show_alert=True)
            return

        with conn.cursor() as cursor:
            cursor.execute(
                'INSERT INTO distribution_agreements (user_id, agreed) VALUES (%s, %s)',
                (call.from_user.id, True)
            )
            conn.commit()

        ask_release_type(call.message)
    except Exception as e:
        logger.error(f"Error saving distribution agreement: {e}")
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data == "distribution_start")
def start_distribution_form(call):
    """Start distribution form"""
    user_id = call.from_user.id
    bot.distribution_forms = getattr(bot, 'distribution_forms', {})
    bot.distribution_forms[user_id] = DistributionForm()

    # Start with first field
    form = bot.distribution_forms[user_id]
    form.current_field = 0
    form.message_id = call.message.message_id
    form.chat_id = call.message.chat.id

    show_distribution_question(call.message.chat.id, call.message.message_id, form)
    bot.register_next_step_handler(call.message, process_distribution_form)




@bot.callback_query_handler(func=lambda call: call.data == "distribution_prev")
def handle_distribution_prev(call):
    """Handle previous question button"""
    user_id = call.from_user.id
    if user_id not in bot.distribution_forms:
        bot.answer_callback_query(call.id, "❌ Форма не найдена. Начните заново.")
        return
    
    form = bot.distribution_forms[user_id]
    if form.current_field > 0:
        form.current_field -= 1
        show_distribution_question(call.message.chat.id, call.message.message_id, form)
        bot.answer_callback_query(call.id)
    else:
        bot.answer_callback_query(call.id, "Это первый вопрос", show_alert=True)




@bot.callback_query_handler(func=lambda call: call.data == "distribution_edit")
def handle_distribution_edit(call):
    """Handle edit information button"""
    user_id = call.from_user.id
    if user_id not in bot.distribution_forms:
        bot.answer_callback_query(call.id, "❌ Форма не найдена. Начните заново.")
        return
    
    form = bot.distribution_forms[user_id]
    field_name, _ = form.fields[form.current_field]
    
    # Очищаем текущий ответ
    form.data[field_name] = ""
    
    # Показываем вопрос без ответа
    show_distribution_question(call.message.chat.id, call.message.message_id, form)
    bot.answer_callback_query(call.id, "Введите новый ответ")
    
    # Регистрируем обработчик для нового ответа
    bot.register_next_step_handler(call.message, process_distribution_form)




@bot.callback_query_handler(func=lambda call: call.data.startswith("design_brief_"))
def handle_design_brief_request(call):
    service = call.data.split("_", 2)[2]
    if service not in DESIGN_BRIEF_TEMPLATES:
        bot.answer_callback_query(call.id, "Шаблон недоступен.", show_alert=True)
        return
    bot.answer_callback_query(call.id)
    prompt_design_brief(call.from_user.id, service)




@bot.callback_query_handler(func=lambda call: call.data == "idist_start")
def improved_distribution_start(call):
    user_id = call.from_user.id
    if not hasattr(bot, 'improved_distribution_forms'):
        bot.improved_distribution_forms = {}
    
    form = ImprovedDistributionForm()
    form.chat_id = call.message.chat.id
    form.message_id = call.message.message_id
    form.user_id = user_id
    bot.improved_distribution_forms[user_id] = form
    
    show_improved_distribution_step(form.chat_id, form.message_id, form)
    bot.register_next_step_handler(call.message, process_improved_distribution_input)




@bot.callback_query_handler(func=lambda call: call.data == "idist_prev")
def improved_dist_prev(call):
    user_id = call.from_user.id
    if user_id not in bot.improved_distribution_forms:
        return
    form = bot.improved_distribution_forms[user_id]
    if form.current_step > 0:
        form.current_step -= 1
    show_improved_distribution_step(form.chat_id, form.message_id, form)
    bot.answer_callback_query(call.id)




@bot.callback_query_handler(func=lambda call: call.data == "idist_edit")
def improved_dist_edit(call):
    user_id = call.from_user.id
    if user_id not in bot.improved_distribution_forms:
        return
    form = bot.improved_distribution_forms[user_id]
    step = form.get_current_step()
    if step:
        field_name = step[0]
        form.data.pop(field_name, None)
    show_improved_distribution_step(form.chat_id, form.message_id, form)
    bot.answer_callback_query(call.id, "Введите новое значение")




@bot.callback_query_handler(func=lambda call: call.data == "idist_cancel_all")
def improved_dist_cancel_all(call):
    user_id = call.from_user.id
    if user_id not in bot.improved_distribution_forms:
        return
    
    form = bot.improved_distribution_forms[user_id]
    
    # Спрашиваем о сохранении в черновик
    if form.data:
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("💾 Да, сохранить", callback_data="idist_save_and_cancel"),
            types.InlineKeyboardButton("❌ Нет, удалить", callback_data="idist_delete_and_cancel")
        )
        try:
            bot.edit_message_text(
                "❌ Отмена создания релиза\n\nСохранить как черновик?",
                form.chat_id,
                form.message_id,
                reply_markup=markup
            )
        except:
            pass
    else:
        bot.improved_distribution_forms.pop(user_id, None)
        bot.answer_callback_query(call.id, "❌ Отменено")




@bot.callback_query_handler(func=lambda call: call.data == "idist_preview")
def improved_dist_preview(call):
    user_id = call.from_user.id
    if user_id not in bot.improved_distribution_forms:
        return
    form = bot.improved_distribution_forms[user_id]
    show_improved_distribution_preview(form.chat_id, form.message_id, form)
    bot.answer_callback_query(call.id)




