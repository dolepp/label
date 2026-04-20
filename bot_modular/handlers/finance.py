"""Handlers: register on bot."""
from core.bot import bot
from handlers.common import *  # noqa: F401,F403

@bot.message_handler(func=lambda message: message.text == "🎟 Ввести промокод")
def handle_promo_input(message):
    """Start promo code input flow"""
    bot.reply_to(
        message,
        "🎟 Ввод промокода\n\n"
        "Введите ваш промокод:",
        reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("❌ Отмена")
    )
    bot.register_next_step_handler(message, process_promo_input)




@bot.callback_query_handler(func=lambda call: call.data.startswith("topup_") and not call.data.startswith("topup_pay_"))
def handle_topup_callback(call):
    """Handle fixed or custom top-up amount"""
    if call.data == "topup_custom":
        msg = bot.edit_message_text(
            "Введите сумму пополнения (целое число рублей):",
            call.message.chat.id,
            call.message.message_id
        )
        # Следующий шаг ожидаем обычным сообщением от пользователя
        bot.register_next_step_handler(call.message, process_custom_topup_amount)
        return

    amount = int(call.data.split("_")[1])
    start_balance_payment(call, amount)




@bot.callback_query_handler(func=lambda call: call.data.startswith("topup_pay_"))
def handle_topup_pay(call):
    amount = int(call.data.split("_")[2])
    start_balance_payment(call, amount)




@bot.callback_query_handler(func=lambda call: call.data == "topup_from_profile")
def handle_topup_from_profile(call):
    """Open top-up menu from profile"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    for amount in (300, 500, 1000, 2000):
        markup.add(types.InlineKeyboardButton(f"{amount}₽", callback_data=f"topup_{amount}"))
    markup.add(types.InlineKeyboardButton("Другая сумма", callback_data="topup_custom"))
    markup.add(types.InlineKeyboardButton("◀️ Отмена", callback_data="back_to_profile"))

    try:
        bot.edit_message_text(
            "💳 Пополнение баланса\n\nВыберите сумму:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception:
        bot.send_message(
            call.message.chat.id,
            "💳 Пополнение баланса\n\nВыберите сумму:",
            reply_markup=markup
        )




@bot.callback_query_handler(func=lambda call: call.data.startswith("yookassa_pay_"))
def handle_yookassa_payment(call):
    """Handle YooKassa payment creation"""
    amount = int(call.data.split("_")[2])
    
    # Валидация суммы перед отправкой в YooKassa
    if amount < 50 or amount > 100000:
        bot.answer_callback_query(call.id, "❌ Неверная сумма для платежа", show_alert=True)
        return
    
    # Проверка доступности YooKassa
    if not YOOKASSA_AVAILABLE:
        logger.error("YooKassa module not available")
        bot.answer_callback_query(call.id, "❌ Модуль YooKassa недоступен", show_alert=True)
        return
    
    # Проверка конфигурации YooKassa
    if not Configuration.account_id or not Configuration.secret_key:
        logger.error("YooKassa configuration missing")
        bot.answer_callback_query(call.id, "❌ Не настроена конфигурация YooKassa", show_alert=True)
        return
    
    # Проверка статуса YooKassa API (временно отключена для тестирования)
    # status_ok, status_message = check_yookassa_status()
    # if not status_ok:
    #     logger.error(f"YooKassa API check failed: {status_message}")
    #     bot.answer_callback_query(call.id, f"❌ YooKassa недоступен: {status_message}", show_alert=True)
    #     return
    logger.info("YooKassa API check skipped - attempting direct payment creation")
    
    logger.info(f"Creating YooKassa payment for user {call.from_user.id}, amount: {amount}")
    
    # Create YooKassa payment
    try:
        payment_data = {
            "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
            "confirmation": {"type": "redirect", "return_url": "https://t.me/twaslabel_bot"},
            "capture": True,
            "description": f"Пополнение баланса пользователя {call.from_user.id}",
            "metadata": {
                "user_id": str(call.from_user.id), 
                "service": "topup"
            }
        }
        
        logger.info(f"YooKassa payment data: {payment_data}")
        payment = Payment.create(payment_data)

        payment_url = payment.confirmation.confirmation_url
        payment_id = payment.id
        
        logger.info(f"Created YooKassa payment {payment_id}, amount: {amount}")
        
        # Save order to database
        conn = get_pg_connection()
        if not conn:
            bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
            return
        
        try:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO orders (user_id, service_type, amount, status, payment_id, created_date) VALUES (%s, %s, %s, %s, %s, %s)',
                (call.from_user.id, "topup", amount, "pending", payment_id, datetime.now())
            )
            conn.commit()
            
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("💳 Перейти к оплате", url=payment_url),
                types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_payment_{payment_id}")
            )
            
            # Добавляем кнопку отмены
            markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_topup"))

            bot.edit_message_text(
                f"💳 Пополнение на {amount}₽ через YooKassa\n\nНажмите для оплаты, затем проверьте статус.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            
        except Error as e:
            logger.error(f"DB error in YooKassa payment: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка при создании платежа", show_alert=True)
        finally:
            if conn:
                cursor.close()
                return_pg_connection(conn)
            
    except Exception as e:
        logger.error(f"Failed to create YooKassa payment: {e}")
        logger.error(f"YooKassa error details: {type(e).__name__}: {str(e)}")
        
        # Более детальная обработка ошибок YooKassa
        error_message = "❌ Ошибка при создании платежа в YooKassa"
        if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
            error_message += f"\nКод ошибки: {e.response.status_code}"
        if hasattr(e, 'response') and hasattr(e.response, 'text'):
            error_message += f"\nДетали: {e.response.text[:200]}"
        
        bot.answer_callback_query(call.id, error_message, show_alert=True)
        
        # Предлагаем альтернативные способы оплаты
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💳 Crypto Bot", callback_data=f"crypto_pay_{amount}"))
        markup.add(types.InlineKeyboardButton("⭐ Telegram Stars", callback_data=f"stars_pay_{amount}"))
        markup.add(types.InlineKeyboardButton("🔄 Попробовать снова", callback_data=f"yookassa_pay_{amount}"))
        
        bot.edit_message_text(
            f"❌ Ошибка при создании платежа в YooKassa\n\n"
            f"Попробуйте другие способы оплаты:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )




@bot.callback_query_handler(func=lambda call: call.data.startswith("stars_pay_"))
def handle_stars_payment(call):
    """Handle Telegram Stars payment creation"""
    amount = int(call.data.split("_")[2])
    
    # Валидация суммы
    if amount < 50 or amount > 100000:
        bot.answer_callback_query(call.id, "❌ Неверная сумма для платежа", show_alert=True)
        return
    
    try:
        # Create Telegram Stars payment
        stars_payment_id = f"stars_{call.from_user.id}_{int(time.time())}"
        
        # Save order to database
        conn = get_pg_connection()
        if not conn:
            bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
            return
        
        try:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO orders (user_id, service_type, amount, status, payment_id, created_date) VALUES (%s, %s, %s, %s, %s, %s)',
                (call.from_user.id, "topup", amount, "pending", stars_payment_id, datetime.now())
            )
            conn.commit()
            
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("⭐ Оплатить Stars", callback_data=f"pay_stars_{stars_payment_id}"),
                types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_stars_{stars_payment_id}")
            )
            
            markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_topup"))

            bot.edit_message_text(
                f"⭐ Пополнение на {amount}₽ через Telegram Stars\n\n"
                f"Для оплаты нажмите кнопку 'Оплатить Stars' и следуйте инструкциям.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            
        except Error as e:
            logger.error(f"DB error in Stars payment: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка при создании платежа", show_alert=True)
        finally:
            if conn:
                cursor.close()
                return_pg_connection(conn)
                
    except Exception as e:
        logger.error(f"Failed to create Stars payment: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при создании платежа в Stars", show_alert=True)




@bot.callback_query_handler(func=lambda call: call.data.startswith("crypto_pay_"))
def handle_crypto_payment(call):
    """Handle Crypto Bot payment creation"""
    payment_id = call.data.split("_")[2]
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT amount FROM orders WHERE payment_id = %s', (payment_id,))
        result = cursor.fetchone()
        
        if not result:
            bot.answer_callback_query(call.id, "❌ Заказ не найден", show_alert=True)
            return
        
        amount = result[0]
        
        # Create Crypto Bot payment link
        # Note: This is a placeholder. You'll need to integrate with actual Crypto Bot API
        crypto_payment_url = f"https://t.me/CryptoBot?start=pay_{payment_id}_{amount}"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("₿ Оплатить через Crypto Bot", url=crypto_payment_url),
            types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_payment_{payment_id}")
        )

        bot.edit_message_text(
            f"Пополнение на {amount}₽ через Crypto Bot\n\n"
            f"Нажмите кнопку ниже для перехода к оплате в Crypto Bot.\n"
            f"После оплаты нажмите 'Проверить оплату'.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
    except Error as e:
        logger.error(f"DB error in Crypto payment: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при создании платежа", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("check_payment_"))
def check_payment_status(call):
    """Check payment status"""
    payment_id = call.data.split("_")[2]
    user_id = call.from_user.id
    
    # Мгновенно отвечаем на нажатие, чтобы Telegram не показывал таймаут
    try:
        bot.answer_callback_query(call.id, "🔎 Проверяю оплату...")
    except Exception:
        pass
    
    # Сначала проверяем, есть ли заказ в базе данных
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        # Ищем заказ по payment_id (может быть как оригинальный order_xxx, так и YooKassa ID)
        cursor.execute('SELECT amount, service_type, status, user_id FROM orders WHERE payment_id = %s', (payment_id,))
        order_info = cursor.fetchone()
        
        if not order_info:
            # Если заказ не найден, попробуем получить его из metadata платежа YooKassa
            try:
                payment = Payment.find_one(payment_id)
                if payment and hasattr(payment, 'metadata') and payment.metadata.get('order_id'):
                    original_order_id = payment.metadata['order_id']
                    cursor.execute('SELECT amount, service_type, status, user_id FROM orders WHERE payment_id = %s', (original_order_id,))
                    order_info = cursor.fetchone()
                    logger.info(f"Found order via YooKassa metadata: {original_order_id}")
            except Exception as e:
                logger.error(f"Failed to get payment metadata: {e}")
            
        if not order_info:
            logger.error(f"Order not found for payment_id: {payment_id}")
            bot.answer_callback_query(call.id, "❌ Заказ не найден в базе данных", show_alert=True)
            return
        
        amount, service_type, order_status, order_user_id = order_info
        
        # Проверяем, что пользователь является владельцем заказа
        if order_user_id != user_id:
            logger.warning(f"User {user_id} trying to check payment for order owned by {order_user_id}")
            bot.answer_callback_query(call.id, "❌ Это не ваш заказ", show_alert=True)
            return
        
        # Если заказ уже завершен, показываем сообщение
        if order_status == "completed":
            bot.answer_callback_query(call.id, "✅ Этот заказ уже оплачен и обработан", show_alert=True)
            return
        
        # Проверяем статус платежа в YooKassa
        payment = None
        try:
            payment = Payment.find_one(payment_id)
            logger.info(f"Payment {payment_id} status: {getattr(payment, 'status', 'unknown')}")
        except Exception as e:
            logger.error(f"Error fetching payment {payment_id} from YooKassa: {e}")
            # Если не можем получить статус от YooKassa, проверяем возраст заказа
            try:
                cursor.execute('SELECT created_date FROM orders WHERE payment_id = %s', (payment_id,))
                created_date_result = cursor.fetchone()
                if created_date_result:
                    created_date = created_date_result[0]
                    # Если заказ старше 1 часа и статус pending, считаем его неуспешным
                    if (datetime.now() - created_date).total_seconds() > 3600:  # 1 час
                        bot.answer_callback_query(call.id, "❌ Время ожидания платежа истекло. Создайте новый заказ.", show_alert=True)
                        return
            except Exception as date_error:
                logger.error(f"Error checking order date: {date_error}")
            
            bot.answer_callback_query(call.id, "❌ Не удалось проверить статус платежа. Попробуйте позже.", show_alert=True)
            return

        if not payment:
            bot.answer_callback_query(call.id, "❌ Платеж не найден в системе YooKassa", show_alert=True)
            return

        status = getattr(payment, 'status', None)
        logger.info(f"Payment {payment_id} final status: {status}")
        
        if status == "succeeded":
            handle_successful_payment(call, payment)
        elif status in ("pending", "waiting_for_capture", "waiting_for_payment"):
            bot.answer_callback_query(call.id, "⏳ Оплата еще не получена. Попробуйте позже.", show_alert=True)
        elif status == "canceled":
            bot.answer_callback_query(call.id, "❌ Платеж отменен", show_alert=True)
        else:
            bot.answer_callback_query(call.id, f"❌ Статус платежа: {status}", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error in check_payment_status: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при проверке платежа", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data == "finance_stats")
def handle_finance_stats(call):
    """Handle detailed finance statistics with monthly breakdown"""
    bot.answer_callback_query(call.id)
    conn = get_pg_connection()
    if not conn:
        bot.edit_message_text(
            "❌ Ошибка подключения к базе данных. Попробуйте позже.",
            call.message.chat.id,
            call.message.message_id
        )
        return

    try:
        cursor = conn.cursor()
        
        # Get total revenue
        cursor.execute('SELECT SUM(amount) FROM orders WHERE status = %s', ("completed",))
        result_total = cursor.fetchone()
        total_revenue = float(result_total[0]) if result_total and result_total[0] is not None else 0.0
        
        # Calculate Artem's share (15%)
        artem_share = total_revenue * 0.15
        remaining_income = total_revenue - artem_share
        
        # Get monthly revenue for current month
        current_month = datetime.now().replace(day=1)
        cursor.execute('''
            SELECT SUM(amount) FROM orders 
            WHERE status = %s AND created_date >= %s
        ''', ("completed", current_month))
        result_month = cursor.fetchone()
        monthly_revenue = float(result_month[0]) if result_month and result_month[0] is not None else 0.0
        
        # Calculate monthly Artem's share
        monthly_artem_share = monthly_revenue * 0.15
        monthly_remaining = monthly_revenue - monthly_artem_share
        
        # Get today's revenue
        today = datetime.now().date()
        cursor.execute('SELECT SUM(amount) FROM orders WHERE status = %s AND DATE(created_date) = %s',
                       ("completed", today,))
        result_today = cursor.fetchone()
        today_revenue = float(result_today[0]) if result_today and result_today[0] is not None else 0.0
        
        # Calculate today's Artem's share
        today_artem_share = today_revenue * 0.15
        today_remaining = today_revenue - today_artem_share

        stats_text = (
            "📊 Подробная финансовая статистика\n\n"
            f"💰 Общий доход: {total_revenue:,.2f}₽\n"
            f"👤 Доля Артёма (15%): {artem_share:,.2f}₽\n"
            f"🏢 Оставшийся доход: {remaining_income:,.2f}₽\n\n"
            f"📅 Доход за месяц: {monthly_revenue:,.2f}₽\n"
            f"👤 Доля Артёма за месяц: {monthly_artem_share:,.2f}₽\n"
            f"🏢 Оставшийся доход за месяц: {monthly_remaining:,.2f}₽\n\n"
            f"📆 Доход за сегодня: {today_revenue:,.2f}₽\n"
            f"👤 Доля Артёма за сегодня: {today_artem_share:,.2f}₽\n"
            f"🏢 Оставшийся доход за сегодня: {today_remaining:,.2f}₽"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(
            types.InlineKeyboardButton("◀️ Назад", callback_data="admin_finance")
        )

        bot.edit_message_text(
            stats_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Error as e:
        logger.error(f"PostgreSQL error in handle_finance_stats: {e}")
        bot.edit_message_text(
            "❌ Произошла ошибка при получении подробной статистики.",
            call.message.chat.id,
            call.message.message_id
        )
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data == "finance_promo")
def handle_finance_promo(call):
    """Handle promo codes management from finance menu"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Создать промокод", callback_data="promo_create"),
        types.InlineKeyboardButton("📊 Статистика промокодов", callback_data="promo_stats"),
        types.InlineKeyboardButton("❌ Удалить промокоды", callback_data="promo_delete"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_finance")
    )

    bot.edit_message_text(
        "🎟 Управление промокодами",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )




@bot.callback_query_handler(func=lambda call: call.data == "promo_create")
def handle_promo_create(call):
    """Handle promo code creation request"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔢 С ограничением по использованию", callback_data="promo_create_limited"),
        types.InlineKeyboardButton("⏰ С ограничением по времени", callback_data="promo_create_timed"),
        types.InlineKeyboardButton("♾️ Без ограничений", callback_data="promo_create_unlimited"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="finance_promo")
    )
    
    bot.edit_message_text(
        "🎟 Создание промокода\n\n"
        "Выберите тип промокода:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )




@bot.callback_query_handler(func=lambda call: call.data == "promo_create_timed")
def handle_promo_create_timed(call):
    """Handle promo code creation with time limit"""
    bot.edit_message_text(
        "⏰ Создание промокода с ограничением по времени\n\n"
        "Введите данные в формате:\n"
        "КОД СУММА ДАТА_ОКОНЧАНИЯ\n\n"
        "Например: SUMMER2024 500 31.12.2024\n"
        "Формат даты: ДД.ММ.ГГГГ",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(call.message, process_promo_create_timed)




@bot.callback_query_handler(func=lambda call: call.data == "promo_stats")
def handle_promo_stats(call):
    """Handle promo codes statistics"""
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Get total promo codes
        cursor.execute('SELECT COUNT(*) FROM promo_codes')
        total = cursor.fetchone()[0]
        
        # Get active promo codes
        cursor.execute('SELECT COUNT(*) FROM promo_codes WHERE is_active = TRUE')
        active = cursor.fetchone()[0]
        
        # Get expired promo codes
        cursor.execute('SELECT COUNT(*) FROM promo_codes WHERE expires_at < CURRENT_TIMESTAMP AND expires_at IS NOT NULL')
        expired = cursor.fetchone()[0]
        
        # Get promo codes with usage limits
        cursor.execute('SELECT COUNT(*) FROM promo_codes WHERE max_uses IS NOT NULL')
        limited_usage = cursor.fetchone()[0]
        
        # Get total amount from all codes
        cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM promo_codes')
        total_amount = cursor.fetchone()[0]
        
        # Get total amount from used codes
        cursor.execute('SELECT COALESCE(SUM(amount), 0) FROM promo_codes WHERE current_uses > 0')
        used_amount = cursor.fetchone()[0]
        
        stats_text = (
            "📊 Статистика промокодов\n\n"
            f"Всего промокодов: {total}\n"
            f"Активных: {active}\n"
            f"Истекших: {expired}\n"
            f"С лимитом использований: {limited_usage}\n"
            f"Общая сумма всех: {total_amount}₽\n"
            f"Сумма использованных: {used_amount}₽"
        )
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="finance_promo"))
        
        bot.edit_message_text(
            stats_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
    except Error as e:
        logger.error(f"PostgreSQL error in promo stats: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка получения статистики", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_promo_"))
def handle_delete_promo(call):
    """Handle specific promo code deletion"""
    code = call.data.split("_")[2]
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM promo_codes WHERE code = %s AND is_used = FALSE', (code,))
        
        if cursor.rowcount > 0:
            conn.commit()
            bot.answer_callback_query(call.id, f"✅ Промокод {code} удален")
            
            # Return to promo management
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="finance_promo"))
            
            bot.edit_message_text(
                f"✅ Промокод {code} успешно удален",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
        else:
            bot.answer_callback_query(call.id, "❌ Промокод не найден или уже использован", show_alert=True)
            
    except Error as e:
        logger.error(f"PostgreSQL error in delete promo: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка удаления промокода", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data == "skip_channel")
def skip_channel_handler(call):
    """Handle skipping channel input"""
    try:
        # Подключаемся к PostgreSQL
        conn = get_pg_connection()
        if not conn:
            bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных. Попробуйте позже.")
            return

        cursor = conn.cursor()
        username = call.from_user.username

        # Обновляем запись в таблице label, добавляя "не указал" в колонку kanal
        cursor.execute("""
            UPDATE label 
            SET kanal = %s 
            WHERE tg = %s
        """, ("не указал", username))

        conn.commit()
        logger.info(f"User {username} skipped channel input")

        # Создаем клавиатуру главного меню
        markup = create_main_menu()

        # Отправляем сообщение о завершении регистрации
        bot.edit_message_text(
            "✅ Регистрация успешно завершена!\n\n"
            "Теперь вы можете пользоваться всеми функциями бота.\n\n"
            "Выберите действие в меню ниже 👇",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    except Exception as e:
        logger.error(f"Error handling skip_channel: {e}")
        bot.answer_callback_query(call.id, "❌ Произошла ошибка. Попробуйте позже.")

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'conn' in locals() and conn:
            return_pg_connection(conn)




