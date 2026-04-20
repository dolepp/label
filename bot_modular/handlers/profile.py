"""Handlers: register on bot."""
from core.bot import bot
from handlers.common import *  # noqa: F401,F403

@bot.message_handler(func=lambda message: message.text == "📀 Мои релизы")
@require_channel_subscription
def handle_my_releases_command(message, user_id=None):
    """Entry point for viewing releases with subscription check"""
    handle_my_releases(message, user_id=user_id, admin_mode=False)




@bot.message_handler(func=lambda message: message.text == "🆘 Мои заявки")
def handle_my_support_requests(message):
    """Show user's support requests"""
    user_id = message.from_user.id
    requests = get_user_support_requests(user_id)

    if not requests:
        bot.reply_to(message, "🆘 У вас пока нет заявок поддержки.")
        return

    text_lines = ["🆘 Ваши заявки поддержки:\n"]
    for req in sorted(requests, key=lambda x: x["created_at"], reverse=True)[:10]:
        text_lines.append(
            f"• {req['template_title']} | {req['status']} | {format_human_datetime(req['created_at'])}"
        )
    text_lines.append("\nСтатусы обновляются автоматически. Если нужна новая заявка — выберите её в разделе «Помощь» на главном экране.")

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile"))

    bot.reply_to(message, "\n".join(text_lines), reply_markup=markup)




@bot.message_handler(func=lambda message: message.text == "👥 Пригласи друга")
def handle_invite_friend(message):
    """Handle invite friend button from profile menu"""
    user_id = message.from_user.id
    username = message.from_user.username
    
    try:
        conn = get_pg_connection()
        if not conn:
            bot.reply_to(message, "❌ Ошибка подключения к базе данных", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("◀️ Назад в профиль"))
            return
        
        cursor = conn.cursor()
        
        # Проверяем, есть ли у пользователя реферальный код
        cursor.execute('''
            SELECT COALESCE(referral_code, '') as referral_code, 
                   COALESCE(referral_count, 0) as referral_count, 
                   COALESCE(referral_earnings, 0) as referral_earnings
            FROM label 
            WHERE telegram_id = %s
        ''', (user_id,))
        result = cursor.fetchone()
        
        if result:
            referral_code, referral_count, referral_earnings = result
            
            # Если реферального кода нет, создаем его
            if not referral_code:
                referral_code = generate_referral_code(user_id)
                if not referral_code:
                    bot.reply_to(message, "❌ Ошибка при создании реферального кода", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("◀️ Назад в профиль"))
                    return
            
            # Создаем реферальную ссылку
            bot_username = bot.get_me().username
            referral_link = f"https://t.me/{bot_username}?start={referral_code}"
            
            referral_text = "👥 Пригласите друзей и получайте бонусы!\n\n"
            referral_text += f"🔗 Ваша реферальная ссылка:\n`{referral_link}`\n\n"
            referral_text += f"📊 Статистика:\n"
            referral_text += f"👥 Приглашено друзей: {referral_count or 0}\n"
            referral_text += f"💰 Заработано: {referral_earnings or 0}₽\n\n"
            referral_text += f"💡 Как это работает:\n"
            referral_text += f"• Отправьте ссылку другу\n"
            referral_text += f"• Друг регистрируется по ссылке\n"
            referral_text += f"• Вы получаете 100₽ на баланс\n"
            referral_text += f"• Друг получает 50₽ на баланс\n\n"
            share_url = f"https://t.me/share/url?url={quote(referral_link)}&text=Присоединяйся к TWAS Label! 🎵"
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📤 Поделиться ссылкой", url=share_url))
            
            bot.reply_to(message, referral_text, reply_markup=markup, parse_mode='Markdown')
        else:
            bot.reply_to(message, "❌ Профиль не найден", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("◀️ Назад в профиль"))
            
    except Exception as e:
        logger.error(f"Error handling invite friend: {e}")
        bot.reply_to(message, "❌ Ошибка при получении реферальной информации", reply_markup=types.ReplyKeyboardMarkup(resize_keyboard=True).add("◀️ Назад в профиль"))
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data == "back_to_profile")
def back_to_profile_handler(call):
    """Return to profile view"""
    # Delete current message
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass

    # Show profile
    user_id = call.from_user.id
    username = call.from_user.username
    show_profile(call.message.chat.id, user_id, username)




@bot.message_handler(func=lambda message: message.text == "✏️ Редактировать профиль")
def show_profile_edit_options(message):
    """Show profile editing options"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    buttons = [
        "🎤 Изменить имя артиста",
        "📺 Изменить канал",
        "👥 Изменить ФИО",
        "📧 Изменить email",  # Новая кнопка
        "◀️ Назад в профиль"
    ]
    markup.add(*buttons)

    bot.reply_to(
        message,
        "Выберите, что хотите изменить:",
        reply_markup=markup
    )




@bot.message_handler(func=lambda message: message.text == "◀️ Назад в профиль")
def back_to_profile(message):
    """Return to profile view"""
    # Обновляем клавиатуру профиля
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("✏️ Редактировать профиль"))
    markup.add(types.KeyboardButton("📀 Мои релизы"))
    markup.add(types.KeyboardButton("📊 Мои отчеты"))
    markup.add(types.KeyboardButton("💳 Пополнить баланс"))
    markup.add(types.KeyboardButton("🎟 Ввести промокод"))
    markup.add(types.KeyboardButton("◀️ Назад в меню"))

    bot.reply_to(
        message,
        "Возвращаемся в профиль...",
        reply_markup=markup
    )




@bot.callback_query_handler(func=lambda call: call.data == "profile_data")
def handle_profile_data(call):
    """Handle profile data request"""
    user_id = call.from_user.id
    
    try:
        conn = get_pg_connection()
        if not conn:
            bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
            return
        
        cursor = conn.cursor()
        cursor.execute('''
            SELECT name, kanal, fio, email, COALESCE(balance, 0)
            FROM label 
            WHERE telegram_id = %s
        ''', (user_id,))
        user_info = cursor.fetchone()
        
        if user_info:
            name, kanal, fio, email, balance = user_info
            
            profile_text = "📝 Ваши данные:\n\n"
            profile_text += f"🎤 Имя артиста: {name or 'Не указано'}\n"
            profile_text += f"📺 Канал: {kanal or 'Не указан'}\n"
            profile_text += f"👥 ФИО: {fio or 'Не указано'}\n"
            profile_text += f"📧 Email: {email or 'Не указан'}\n"
            profile_text += f"💰 Баланс: {balance:,.2f}₽"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✏️ Редактировать", callback_data="edit_profile_data"))
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_profile"))
            
            bot.edit_message_text(
                profile_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
        else:
            bot.answer_callback_query(call.id, "❌ Профиль не найден", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error handling profile data: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при получении данных", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data == "profile_releases")
def handle_profile_releases(call):
    """Handle profile releases request"""
    user_id = call.from_user.id
    
    try:
        conn = get_pg_connection()
        if not conn:
            bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
            return
        
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, release_name, release_date, status 
            FROM releases 
            WHERE user_id = %s
            ORDER BY release_date DESC
            LIMIT 10
        ''', (user_id,))
        releases = cursor.fetchall()
        
        if releases:
            releases_text = "💿 Ваши релизы:\n\n"
            for i, (release_id, name, date, status) in enumerate(releases, 1):
                date_str = date.strftime('%d.%m.%Y') if date else 'Дата не указана'
                releases_text += f"{i}. {name} ({date_str}) - {status}\n"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📀 Все релизы", callback_data="all_releases"))
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_profile"))
            
            bot.edit_message_text(
                releases_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
        else:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("➕ Создать релиз", callback_data="create_release"))
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_profile"))
            
            bot.edit_message_text(
                "💿 У вас пока нет релизов\n\nСоздайте свой первый релиз!",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            
    except Exception as e:
        logger.error(f"Error handling profile releases: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при получении релизов", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data == "profile_orders")
def handle_profile_orders(call):
    """Handle profile orders request"""
    user_id = call.from_user.id
    
    try:
        conn = get_pg_connection()
        if not conn:
            bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
            return
        
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, service_type, amount, status, created_date 
            FROM orders 
            WHERE user_id = %s
            ORDER BY created_date DESC
            LIMIT 10
        ''', (user_id,))
        orders = cursor.fetchall()
        
        if orders:
            orders_text = "🛍 Ваши заказы:\n\n"
            for i, (order_id, service, amount, status, date) in enumerate(orders, 1):
                date_str = date.strftime('%d.%m.%Y') if date else 'Дата не указана'
                orders_text += f"{i}. Заказ #{order_id} ({service}) - {amount}₽ - {status} ({date_str})\n"
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("🛍 Все заказы", callback_data="all_orders"))
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_profile"))
            
            bot.edit_message_text(
                orders_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
        else:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("💳 Пополнить баланс", callback_data="topup_from_profile"))
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_profile"))
            
            bot.edit_message_text(
                "🛍 У вас пока нет заказов\n\nПополните баланс и создайте заказ!",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            
    except Exception as e:
        logger.error(f"Error handling profile orders: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при получении заказов", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data == "profile_drafts")
def show_profile_drafts(call):
    user_id = call.from_user.id
    
    try:
        conn = get_pg_connection()
        if not conn:
            bot.answer_callback_query(call.id, "❌ Ошибка БД")
            return
        
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, draft_type, current_step, created_at FROM drafts WHERE user_id = %s ORDER BY updated_at DESC LIMIT 10',
            (user_id,)
        )
        
        drafts = cursor.fetchall()
        cursor.close()
        return_pg_connection(conn)
        
        if not drafts:
            text = "📋 Черновики\n\nУ вас пока нет сохранённых черновиков."
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="profile"))
        else:
            text = f"📋 Ваши черновики ({len(drafts)})\n\n"
            markup = types.InlineKeyboardMarkup(row_width=1)
            
            for draft_id, draft_type, current_step, created_at in drafts:
                btn_text = f"📝 {draft_type} - Шаг {current_step} ({created_at.strftime('%d.%m.%Y')})"
                markup.add(types.InlineKeyboardButton(btn_text, callback_data=f"draft_load_{draft_id}"))
            
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="profile"))
        
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        except:
            pass
        
        bot.answer_callback_query(call.id)
        
    except Exception as e:
        logger.error(f"Error showing drafts: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка")



