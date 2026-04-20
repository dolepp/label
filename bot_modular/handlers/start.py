"""Handlers: register on bot."""
from core.bot import bot
from handlers.common import *  # noqa: F401,F403

@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def handle_subscription_check(call):
    """Обработка проверки подписки после нажатия кнопки 'Я подписался'"""
    user_id = call.from_user.id
    
    if check_channel_subscription(user_id, force_check=True):
        bot.answer_callback_query(call.id, "✅ Отлично! Теперь вы можете пользоваться ботом!")
        
        # Показываем главное меню
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(
            types.KeyboardButton("📀 Мои релизы"),
            types.KeyboardButton("📊 Статистика"),
            types.KeyboardButton("💳 Пополнить баланс"),
            types.KeyboardButton("👤 Профиль"),
            types.KeyboardButton("📞 Поддержка"),
            types.KeyboardButton("ℹ️ О нас")
        )
        
        bot.edit_message_text(
            f"<code>{details}</code>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
        
        bot.send_message(
            call.message.chat.id,
            "🎵 Добро пожаловать в TWAS Label Studio!\n\n"
            "Выберите нужную опцию из меню:",
            reply_markup=markup
        )
    else:
        bot.answer_callback_query(
            call.id, 
            "❌ Подписка не найдена. Пожалуйста, подпишитесь на канал и попробуйте снова.",
            show_alert=True
        )



@bot.message_handler(commands=['start'])
@require_channel_subscription
def start(message):
    """Handle /start command"""
    user_id = message.from_user.id
    username = message.from_user.username

    # Извлекаем реферальный код из команды /start REFERRAL_CODE
    referral_code = None
    if message.text and len(message.text.split()) > 1:
        referral_code = message.text.split()[1].strip()

    try:
        conn = get_pg_connection()
        if not conn:
            bot.reply_to(message, "Извините, произошла ошибка при подключении к базе данных.")
            return

        cursor = conn.cursor()

        # Ищем пользователя по telegram_id и обновляем username (tg), если он указан
        cursor.execute('SELECT id, tg FROM label WHERE telegram_id = %s', (user_id,))
        row = cursor.fetchone()

        is_new_user = False
        if row:
            current_tg = row[1]
            if username and current_tg != username:
                cursor.execute('UPDATE label SET tg = %s WHERE telegram_id = %s', (username, user_id))
            bot.reply_to(message, "С возвращением!")
        else:
            # Пользователь не найден по telegram_id — регистрируем нового
            is_new_user = True
            cursor.execute('SELECT COALESCE(MAX(id), 0) + 1 FROM label')
            result = cursor.fetchone()
            new_id = result[0] if result else 1

            cursor.execute(
                'INSERT INTO label (id, tg, telegram_id, admin, artist, created_date) VALUES (%s, %s, %s, %s, %s, %s)',
                (new_id, username, user_id, 0, 0, datetime.now())
            )
            bot.reply_to(message, "Добро пожаловать! Вы успешно зарегистрированы в системе.")
            logger.info(f"New user registered: {user_id} (username: {username or 'не указан'}) with ID {new_id}")

        conn.commit()

        # Обрабатываем реферальный код
        if referral_code:
            try:
                if is_new_user:
                    cursor.execute('SELECT id FROM referrals WHERE referred_id = %s', (user_id,))
                    existing_referral = cursor.fetchone()
                    if not existing_referral:
                        handle_referral_registration(cursor, user_id, referral_code, conn)
                        conn.commit()
                        logger.info(f"Referral code {referral_code} processed for new user {user_id}")
                    else:
                        notify_referrer_about_visit(referral_code, user_id, username)
                else:
                    notify_referrer_about_visit(referral_code, user_id, username)
            except Exception as e:
                logger.error(f"Error processing referral code {referral_code} for user {user_id}: {e}")
                if is_new_user:
                    conn.rollback()

    except Error as e:
        logger.error(f"Database error in start handler: {e}")
        bot.reply_to(message, "Произошла ошибка при обработке вашего запроса.")
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)

    # Создаем клавиатуру
    markup = create_main_menu()

    # Отправляем приветственное сообщение
    welcome_text = (
        "Добро пожаловать в talk with a star // label  ⭐️\n\n"
        "Мы - музыкальный лейбл и мы поможем вам:\n"
        "• Выпустить трек на все площадки 🎧\n"
        "• Создать обложку для релиза 🎨\n"
        "• Заказать историю к релизу\n"
        "• Получить продвижение 📈\n\n"
        "Используйте меню ниже для навигации 👇\n\n"
        "💡 Команды:\n"
        "/start - Главная страница\n"
        "/main - Вернуться в главное меню\n"
        "/cancel - Отменить текущую операцию"
    )

    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)




@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def callback_check_subscription(call):
    """Handle subscription check callback"""
    if check_subscription(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        start(call.message)
    else:
        bot.answer_callback_query(
            call.id,
            "Окак вы все еще не подписаны на канал. Подпишитесь для использования бота.",
            show_alert=True
        )




@bot.message_handler(commands=['start'])
@require_channel_subscription
def start(message):
    """Handle /start command"""
    user_id = message.from_user.id
    username = message.from_user.username

    # Извлекаем реферальный код из команды /start REFERRAL_CODE
    referral_code = None
    if message.text and len(message.text.split()) > 1:
        referral_code = message.text.split()[1].strip()

    try:
        conn = get_pg_connection()
        if not conn:
            bot.reply_to(message, "Извините, произошла ошибка при подключении к базе данных.")
            return

        cursor = conn.cursor()

        # Ищем пользователя по telegram_id и обновляем username (tg), если он указан
        cursor.execute('SELECT id, tg FROM label WHERE telegram_id = %s', (user_id,))
        row = cursor.fetchone()

        is_new_user = False
        if row:
            current_tg = row[1]
            if username and current_tg != username:
                cursor.execute('UPDATE label SET tg = %s WHERE telegram_id = %s', (username, user_id))
            bot.reply_to(message, "С возвращением!")
        else:
            # Пользователь не найден по telegram_id — регистрируем нового
            is_new_user = True
            cursor.execute('SELECT COALESCE(MAX(id), 0) + 1 FROM label')
            result = cursor.fetchone()
            new_id = result[0] if result else 1

            cursor.execute(
                'INSERT INTO label (id, tg, telegram_id, admin, artist, created_date) VALUES (%s, %s, %s, %s, %s, %s)',
                (new_id, username, user_id, 0, 0, datetime.now())
            )
            bot.reply_to(message, "Добро пожаловать! Вы успешно зарегистрированы в системе.")
            logger.info(f"New user registered: {user_id} (username: {username or 'не указан'}) with ID {new_id}")

        conn.commit()

        # Обрабатываем реферальный код
        if referral_code:
            try:
                if is_new_user:
                    cursor.execute('SELECT id FROM referrals WHERE referred_id = %s', (user_id,))
                    existing_referral = cursor.fetchone()
                    if not existing_referral:
                        handle_referral_registration(cursor, user_id, referral_code, conn)
                        conn.commit()
                        logger.info(f"Referral code {referral_code} processed for new user {user_id}")
                    else:
                        notify_referrer_about_visit(referral_code, user_id, username)
                else:
                    notify_referrer_about_visit(referral_code, user_id, username)
            except Exception as e:
                logger.error(f"Error processing referral code {referral_code} for user {user_id}: {e}")
                if is_new_user:
                    conn.rollback()

    except Error as e:
        logger.error(f"Database error in start handler: {e}")
        bot.reply_to(message, "Произошла ошибка при обработке вашего запроса.")
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)

    # Создаем клавиатуру
    markup = create_main_menu()

    # Отправляем приветственное сообщение
    welcome_text = (
        "Добро пожаловать в talk with a star // label  ⭐️\n\n"
        "Мы - музыкальный лейбл и мы поможем вам:\n"
        "• Выпустить трек на все площадки 🎧\n"
        "• Создать обложку для релиза 🎨\n"
        "• Заказать историю к релизу\n"
        "• Получить продвижение 📈\n\n"
        "Используйте меню ниже для навигации 👇\n\n"
        "💡 Команды:\n"
        "/start - Главная страница\n"
        "/main - Вернуться в главное меню\n"
        "/cancel - Отменить текущую операцию"
    )

    bot.send_message(message.chat.id, welcome_text, reply_markup=markup)




@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def callback_check_subscription(call):
    """Handle subscription check callback"""
    if check_subscription(call.from_user.id):
        bot.delete_message(call.message.chat.id, call.message.message_id)
        start(call.message)
    else:
        bot.answer_callback_query(
            call.id,
            "Окак вы все еще не подписаны на канал. Подпишитесь для использования бота.",
            show_alert=True
        )




