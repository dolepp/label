"""Handlers: register on bot."""
from core.bot import bot
from handlers.common import *  # noqa: F401,F403

@bot.message_handler(func=lambda message: message.text in MAIN_MENU_BUTTONS)
def handle_main_menu(message):
    """Handle main menu button clicks"""
    handlers = {
        "🎵 Наши услуги": handle_services_menu,
        "👤 Мой профиль": handle_profile,
        # "📋 Получить договор": handle_contract_request,  # Временно отключено
        "⭐️ Отзывы": handle_reviews,
        "❓ Помощь/вопросы": handle_help,
        "🌐 Открыть приложение": handle_open_web_app,
        "📊 Статистика": handle_statistics,
        "📞 Поддержка": handle_support,
        "ℹ️ О нас": handle_about
    }

    if message.text in handlers:
        handlers[message.text](message)




@bot.message_handler(commands=['app', 'webapp'])
@require_channel_subscription
def handle_open_web_app_command(message):
    """Handle /app command"""
    send_web_app_link(message.chat.id, message.from_user.id)




@bot.message_handler(func=lambda message: message.text == "◀️ Назад в меню")
def back_to_main_menu(message):
    """Return to main menu"""
    markup = create_main_menu()
    bot.reply_to(message, "Главное меню:", reply_markup=markup)



@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def handle_back_to_main(call):
    """Return to main menu from callback"""
    try:
        # Удаляем текущее сообщение
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        logger.error(f"Error deleting message: {e}")

    # Отправляем главное меню
    markup = create_main_menu()
    menu_text = (
        "🏠 Главное меню\n\n"
        "Выберите нужную опцию из меню ниже 👇"
    )
    bot.send_message(
        call.message.chat.id,
        menu_text,
        reply_markup=markup
    )




@bot.callback_query_handler(func=lambda call: call.data.startswith(("view_contract_", "view_cover_", "view_audio_")))
def handle_view_file(call):
    """Handle viewing release files"""
    action, release_id = call.data.split("_", 1)
    release_id = int(release_id.split("_")[0])
    file_type = action.split("_")[1]  # contract, cover or audio

    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return

    try:
        cursor = conn.cursor()

        # Get file_id based on type
        column_name = {
            'contract': 'contract_file_id',
            'cover': 'cover_file_id',
            'audio': 'audio_file_id'
        }.get(file_type)

        if not column_name:
            bot.answer_callback_query(call.id, "❌ Неверный тип файла", show_alert=True)
            return

        cursor.execute(f'''
            SELECT {column_name} FROM releases WHERE id = %s
        ''', (release_id,))
        result = cursor.fetchone()

        if not result or not result[0]:
            bot.answer_callback_query(call.id, f"❌ Файл не найден", show_alert=True)
            return

        file_id = result[0]

        # Send file based on type
        if file_type == 'contract':
            bot.send_document(call.message.chat.id, file_id, caption="📝 Контракт на релиз")
        elif file_type == 'cover':
            send_file_smart(call.message.chat.id, file_id, caption="🎨 Обложка релиза", file_type_hint='photo')
        elif file_type == 'audio':
            bot.send_audio(call.message.chat.id, file_id, caption="🎧 Аудиофайл релиза")

        bot.answer_callback_query(call.id, "Файл отправлен в чат")

    except Error as e:
        logger.error(f"PostgreSQL error in handle_view_file: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("view_contract_"))
def handle_view_contract(call):
    """Handle user viewing specific contract"""
    contract_id = int(call.data.split("_")[2])
    user_id = call.from_user.id
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Get contract details and check ownership
        cursor.execute('''
            SELECT contract_number, contract_type, status, created_at, completed_at, contract_file_id
            FROM contracts 
            WHERE id = %s AND user_id = %s
        ''', (contract_id, user_id))
        
        contract = cursor.fetchone()
        if not contract:
            bot.answer_callback_query(call.id, "❌ Договор не найден или недоступен", show_alert=True)
            return
        
        contract_number, contract_type, status, created_at, completed_at, contract_file_id = contract
        
        # Format dates
        created_str = created_at.strftime('%d.%m.%Y %H:%M') if created_at else "дата не указана"
        completed_str = completed_at.strftime('%d.%m.%Y %H:%M') if completed_at else "не завершен"
        
        # Status emoji and text
        status_emoji = {
            'pending': '⏳',
            'processing': '🔄',
            'completed': '✅',
            'rejected': '❌'
        }.get(status, '❓')
        
        # Create contract info text
        contract_text = (
            f"📋 Детали договора #{contract_id}\n\n"
            f"📄 Номер: {contract_number}\n"
            f"📋 Тип: {contract_type}\n"
            f"📅 Создан: {created_str}\n"
            f"✅ Завершен: {completed_str}\n"
            f"🔄 Статус: {status_emoji} {status}\n"
        )
        
        if contract_file_id:
            contract_text += f"📎 Файл договора: Прикреплен\n"
        else:
            contract_text += f"📎 Файл договора: Не прикреплен\n"
        
        # Create markup
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        if status == 'completed' and contract_file_id:
            markup.add(types.InlineKeyboardButton("📎 Скачать договор", callback_data=f"download_contract_{contract_id}"))
        
        markup.add(
            types.InlineKeyboardButton("📋 К списку договоров", callback_data="my_contracts"),
            types.InlineKeyboardButton("◀️ Назад в меню", callback_data="back_to_main")
        )
        
        bot.edit_message_text(
            contract_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
        # If contract is completed and has file, send it automatically
        if status == 'completed' and contract_file_id:
            try:
                bot.send_document(
                    call.message.chat.id,
                    contract_file_id,
                    caption=f"📎 Договор #{contract_id}\n\n"
                            f"📄 Номер: {contract_number}\n"
                            f"✅ Статус: Завершен"
                )
            except Exception as e:
                logger.error(f"Error sending contract file: {e}")
                bot.answer_callback_query(call.id, "❌ Ошибка при отправке файла договора", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error viewing contract {contract_id}: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при просмотре договора", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




