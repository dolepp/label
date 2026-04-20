"""Handlers: register on bot."""
from core.bot import bot
from handlers.common import *  # noqa: F401,F403

@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_view_release_"))
def handle_admin_view_release(call):
    """Handle admin request to view release attachments"""
    try:
        # Extract release ID from callback data
        release_id = call.data.split("_")[-1]
        logger.info(f"Admin requested attachments for release: {release_id}")

        conn = get_pg_connection()
        if not conn:
            bot.answer_callback_query(call.id, "❌ Database connection error", show_alert=True)
            return

        cursor = conn.cursor()

        # Get release details
        cursor.execute('''
            SELECT cover_file_id, audio_file_id, contract_file_id, lyrics_file_id
            FROM releases 
            WHERE id = %s
        ''', (release_id,))
        release_files = cursor.fetchone()

        if not release_files:
            bot.answer_callback_query(call.id, "❌ Release not found", show_alert=True)
            return

        # Send files if available
        if release_files[0]:  # Cover
                            send_file_smart(call.message.chat.id, release_files[0], caption="🎨 Release Cover", file_type_hint='photo')

        if release_files[1]:  # Audio
            bot.send_audio(call.message.chat.id, release_files[1], caption="🎧 Audio Track")

        if release_files[2]:  # Contract
            bot.send_document(call.message.chat.id, release_files[2], caption="📝 Beat Contract")

        if release_files[3]:  # Lyrics
            bot.send_document(call.message.chat.id, release_files[3], caption="📜 Song Lyrics")

        # Confirm to admin
        bot.answer_callback_query(call.id, "✅ Attachments sent")

    except Exception as e:
        logger.error(f"Error in handle_admin_view_release: {e}")
        bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.message_handler(commands=['healthcheck', 'diag', 'diagnostics'])
def handle_system_healthcheck(message):
    """Allow admins to run automated system diagnostics"""
    user_id = message.from_user.id
    if not has_access_level(user_id, ["admin"]):
        bot.reply_to(message, "❌ Эта команда доступна только администраторам.")
        return

    diagnostics, overall_status = perform_system_diagnostics()

    response_lines = [
        "🩺 Автоматическая проверка систем завершена",
        f"🕒 {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}",
        ""
    ]

    for item in diagnostics:
        icon = "✅" if item["ok"] else "❌"
        response_lines.append(f"{icon} {item['name']}: {item['details']}")

    response_lines.append("")
    response_lines.append("💡 Все системы работают штатно." if overall_status else "⚠️ Обнаружены проблемы, проверьте логи.")

    bot.reply_to(message, "\n".join(response_lines))




@bot.callback_query_handler(func=lambda call: call.data in ("admin_reviews_pending", "admin_reviews_all"))
def handle_admin_reviews_list(call):
    """Show pending or all reviews to admin"""
    show_pending = call.data.endswith("pending")

    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return

    try:
        cursor = conn.cursor()
        if show_pending:
            cursor.execute('''
                SELECT r.id, l.name, r.service_type, r.rating, r.text, r.created_date
                FROM reviews r
                JOIN label l ON r.user_id = l.telegram_id
                WHERE r.status = 'pending'
                ORDER BY r.created_date DESC
                LIMIT 20
            ''')
            title = "⏳ Отзывы на модерации"
        else:
            cursor.execute('''
                SELECT r.id, l.name, r.service_type, r.rating, r.text, r.created_date, r.status
                FROM reviews r
                JOIN label l ON r.user_id = l.telegram_id
                ORDER BY r.created_date DESC
                LIMIT 20
            ''')
            title = "📚 Все отзывы"

        rows = cursor.fetchall()

        if not rows:
            text = f"{title}\n\nПока пусто."
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_reviews"))
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return

        messages = []
        for row in rows:
            if show_pending:
                review_id, artist_name, service_type, rating, text_body, created_date = row
                stars = "⭐️" * rating
                text = (
                    f"{title}\n\n"
                    f"ID: {review_id}\n"
                    f"👤 {artist_name}\n"
                    f"📂 {service_type}\n"
                    f"{stars}\n"
                    f"💬 {text_body[:300]}{'...' if len(text_body) > 300 else ''}\n"
                    f"📅 {created_date.strftime('%d.%m.%Y')}"
                )
                markup = types.InlineKeyboardMarkup()
                markup.row(
                    types.InlineKeyboardButton("✅ Одобрить", callback_data=f"review_approve_{review_id}"),
                    types.InlineKeyboardButton("❌ Отклонить", callback_data=f"review_reject_{review_id}")
                )
                markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_reviews"))
                messages.append((text, markup))
            else:
                review_id, artist_name, service_type, rating, text_body, created_date, status = row
                stars = "⭐️" * rating
                text = (
                    f"ID: {review_id} • {status}\n"
                    f"👤 {artist_name}\n"
                    f"📂 {service_type}\n"
                    f"{stars}\n"
                    f"💬 {text_body[:300]}{'...' if len(text_body) > 300 else ''}\n"
                    f"📅 {created_date.strftime('%d.%m.%Y')}"
                )
                messages.append((text, None))

        # Если pending — редактируем текущий; если все отзывы — отправим серией сообщений
        if show_pending:
            text, markup = messages[0]
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
            # остальные (если есть) отправим отдельно ниже
            for text, markup in messages[1:]:
                bot.send_message(call.message.chat.id, text, reply_markup=markup)
        else:
            bot.edit_message_text(f"{title}", call.message.chat.id, call.message.message_id)
            for text, _ in messages:
                bot.send_message(call.message.chat.id, text)

    except Error as e:
        logger.error(f"Database error in handle_admin_reviews_list: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при загрузке отзывов", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(
    func=lambda call: call.data.startswith("broadcast_level_") or call.data == "broadcast_create")
def handle_broadcast_callback(call):
    """Handle broadcast level selection and creation"""
    if call.data.startswith("broadcast_level_"):
        handle_admin_broadcast(call)
    elif call.data == "broadcast_create":
        start_broadcast_message(call)




@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_view_release_"))
def handle_admin_view_release(call):
    """Handle admin request to view release attachments"""
    try:
        # Extract release ID from callback data
        release_id = call.data.split("_")[-1]
        logger.info(f"Admin requested attachments for release: {release_id}")

        conn = get_pg_connection()
        if not conn:
            bot.answer_callback_query(call.id, "❌ Database connection error", show_alert=True)
            return

        cursor = conn.cursor()

        # Get release details
        cursor.execute('''
            SELECT cover_file_id, audio_file_id, contract_file_id, lyrics_file_id
            FROM releases 
            WHERE id = %s
        ''', (release_id,))
        release_files = cursor.fetchone()

        if not release_files:
            bot.answer_callback_query(call.id, "❌ Release not found", show_alert=True)
            return

        # Send files if available
        if release_files[0]:  # Cover
                            send_file_smart(call.message.chat.id, release_files[0], caption="🎨 Release Cover", file_type_hint='photo')

        if release_files[1]:  # Audio
            bot.send_audio(call.message.chat.id, release_files[1], caption="🎧 Audio Track")

        if release_files[2]:  # Contract
            bot.send_document(call.message.chat.id, release_files[2], caption="📝 Beat Contract")

        if release_files[3]:  # Lyrics
            bot.send_document(call.message.chat.id, release_files[3], caption="📜 Song Lyrics")

        # Confirm to admin
        bot.answer_callback_query(call.id, "✅ Attachments sent")

    except Exception as e:
        logger.error(f"Error in handle_admin_view_release: {e}")
        bot.answer_callback_query(call.id, f"❌ Error: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data in ("admin_reviews_pending", "admin_reviews_all"))
def handle_admin_reviews_list(call):
    """Show pending or all reviews to admin"""
    show_pending = call.data.endswith("pending")

    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return

    try:
        cursor = conn.cursor()
        if show_pending:
            cursor.execute('''
                SELECT r.id, l.name, r.service_type, r.rating, r.text, r.created_date
                FROM reviews r
                JOIN label l ON r.user_id = l.telegram_id
                WHERE r.status = 'pending'
                ORDER BY r.created_date DESC
                LIMIT 20
            ''')
            title = "⏳ Отзывы на модерации"
        else:
            cursor.execute('''
                SELECT r.id, l.name, r.service_type, r.rating, r.text, r.created_date, r.status
                FROM reviews r
                JOIN label l ON r.user_id = l.telegram_id
                ORDER BY r.created_date DESC
                LIMIT 20
            ''')
            title = "📚 Все отзывы"

        rows = cursor.fetchall()

        if not rows:
            text = f"{title}\n\nПока пусто."
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_reviews"))
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return

        messages = []
        for row in rows:
            if show_pending:
                review_id, artist_name, service_type, rating, text_body, created_date = row
                stars = "⭐️" * rating
                text = (
                    f"{title}\n\n"
                    f"ID: {review_id}\n"
                    f"👤 {artist_name}\n"
                    f"📂 {service_type}\n"
                    f"{stars}\n"
                    f"💬 {text_body[:300]}{'...' if len(text_body) > 300 else ''}\n"
                    f"📅 {created_date.strftime('%d.%m.%Y')}"
                )
                markup = types.InlineKeyboardMarkup()
                markup.row(
                    types.InlineKeyboardButton("✅ Одобрить", callback_data=f"review_approve_{review_id}"),
                    types.InlineKeyboardButton("❌ Отклонить", callback_data=f"review_reject_{review_id}")
                )
                markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_reviews"))
                messages.append((text, markup))
            else:
                review_id, artist_name, service_type, rating, text_body, created_date, status = row
                stars = "⭐️" * rating
                text = (
                    f"ID: {review_id} • {status}\n"
                    f"👤 {artist_name}\n"
                    f"📂 {service_type}\n"
                    f"{stars}\n"
                    f"💬 {text_body[:300]}{'...' if len(text_body) > 300 else ''}\n"
                    f"📅 {created_date.strftime('%d.%m.%Y')}"
                )
                messages.append((text, None))

        # Если pending — редактируем текущий; если все отзывы — отправим серией сообщений
        if show_pending:
            text, markup = messages[0]
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)
            # остальные (если есть) отправим отдельно ниже
            for text, markup in messages[1:]:
                bot.send_message(call.message.chat.id, text, reply_markup=markup)
        else:
            bot.edit_message_text(f"{title}", call.message.chat.id, call.message.message_id)
            for text, _ in messages:
                bot.send_message(call.message.chat.id, text)

    except Error as e:
        logger.error(f"Database error in handle_admin_reviews_list: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при загрузке отзывов", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(
    func=lambda call: call.data.startswith("broadcast_level_") or call.data == "broadcast_create")
def handle_broadcast_callback(call):
    """Handle broadcast level selection and creation"""
    if call.data.startswith("broadcast_level_"):
        handle_admin_broadcast(call)
    elif call.data == "broadcast_create":
        start_broadcast_message(call)




@bot.callback_query_handler(func=lambda call: call.data == "admin_releases")
def handle_admin_releases(call):
    """Handle releases management - show list of users"""
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT telegram_id, tg, name FROM label ORDER BY name')
        users = cursor.fetchall()

        if not users:
            message_text = "🤷‍♀️ В базе данных нет зарегистрированных пользователей."
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))
            bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return

        markup = types.InlineKeyboardMarkup(row_width=1)

        for user_id, username, name in users:
            display_name = f"{name} (@{username})" if name and username else f"ID: {user_id}"
            callback_data = f"user_releases_{user_id}"
            markup.add(types.InlineKeyboardButton(display_name, callback_data=callback_data))

        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))

        bot.edit_message_text(
            "💿 Управление релизами\n\nВыберите пользователя для просмотра его релизов:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Error as e:
        logger.error(f"PostgreSQL error in handle_admin_releases: {e}")
        bot.answer_callback_query(call.id, "❌ Произошла ошибка при получении списка пользователей.", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data == "releases_all")
def show_all_releases(call):
    """Show paginated list of all releases"""
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return

    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT r.artist_name, r.release_name, r.release_date, r.status, l.tg
            FROM releases r
            JOIN label l ON r.user_id = l.telegram_id
            ORDER BY r.release_date DESC
            LIMIT 10
        ''')

        releases = cursor.fetchall()

        if not releases:
            bot.edit_message_text(
                "❌ В базе нет релизов",
                call.message.chat.id,
                call.message.message_id
            )
            return

        releases_text = "📀 Последние 10 релизов:\n\n"
        for artist, name, date, status, username in releases:
            releases_text += (
                f"🎤 <b>{escape_html(artist)}</b> (@{escape_html(username) if username else 'нет username'})\n"
                f"🎵 {escape_html(name)}\n"
                f"📅 {date.strftime('%d.%m.%Y') if date else 'нет даты'}\n"
                f"🟢 {escape_html(status)}\n\n"
            )

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_releases"))

        bot.edit_message_text(
            releases_text,
            call.message.chat.id,
            call.message.message_id,
            parse_mode='HTML',
            reply_markup=markup
        )

    except Error as e:
        logger.error(f"Error in show_all_releases: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("artist_"))
def show_artist_info(call):
    """Show artist information and releases"""
    artist_name = call.data.split("_", 1)[1]

    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return

    try:
        cursor = conn.cursor()

        # Получаем информацию об исполнителе
        cursor.execute('''
            SELECT COUNT(*) as release_count, 
                   MIN(release_date) as first_release,
                   MAX(release_date) as last_release
            FROM releases
            WHERE artist_name = %s
        ''', (artist_name,))

        stats = cursor.fetchone()
        release_count = stats[0] if stats else 0
        first_release = stats[1] if stats and stats[1] else "нет данных"
        last_release = stats[2] if stats and stats[2] else "нет данных"

        # Формируем сообщение с информацией об исполнителе
        artist_info = (
            f"🎤 Исполнитель: {artist_name}\n\n"
            f"📀 Всего релизов: {release_count}\n"
            f"📅 Первый релиз: {first_release}\n"
            f"📅 Последний релиз: {last_release}"
        )

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("📀 Релизы исполнителя", callback_data=f"artist_releases_{artist_name}"),
            types.InlineKeyboardButton("◀️ Назад к списку", callback_data="releases_artists")
        )

        bot.edit_message_text(
            artist_info,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    except Error as e:
        logger.error(f"Error in show_artist_info: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data == "admin_back")
def handle_admin_back(call):
    """Handle back button in admin panel"""
    logger.info(f"admin_back called by user {call.from_user.id}")
    
    # Проверяем права доступа
    user_id = call.from_user.id
    if user_id not in PERMANENT_ADMINS:
        # Проверяем в базе данных
        conn = get_pg_connection()
        if not conn:
            logger.error("Failed to get DB connection in admin_back")
            bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
            return
        
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT admin FROM label WHERE telegram_id = %s', (user_id,))
            result = cursor.fetchone()
            logger.info(f"Admin check result for user {user_id}: {result}")
            
            if not result or result[0] != 1:
                logger.warning(f"User {user_id} tried to access admin_back without rights")
                bot.answer_callback_query(call.id, "❌ У вас нет доступа к этой функции", show_alert=True)
                return
        except Exception as e:
            logger.error(f"Error checking admin rights: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка проверки прав доступа", show_alert=True)
            return
        finally:
            if conn:
                cursor.close()
                return_pg_connection(conn)

    logger.info(f"User {user_id} has admin access, showing admin panel")
    
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
        types.InlineKeyboardButton("📢 Рассылка", callback_data="admin_broadcast"),
        types.InlineKeyboardButton("💿 Релизы", callback_data="admin_releases"),
        types.InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
        types.InlineKeyboardButton("📝 Отзывы", callback_data="admin_reviews"),
        types.InlineKeyboardButton("💰 Финансы", callback_data="admin_finance"),
        types.InlineKeyboardButton("🆘 Поддержка", callback_data="admin_support"),
        types.InlineKeyboardButton("🛒 Заказы", callback_data="admin_orders")
    )

    try:
        bot.edit_message_text(
            "🔐 Панель администратора:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        logger.info("Admin panel successfully displayed")
    except Exception as e:
        logger.error(f"Error displaying admin panel: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)




@bot.callback_query_handler(func=lambda call: call.data == "admin_templates")
def handle_templates_management(call):
    """Handle templates management"""
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✉️ Шаблон письма", callback_data="template_email"),
        types.InlineKeyboardButton("📝 Шаблон договора", callback_data="template_contract"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_services")
    )
    bot.edit_message_text(
        "📝 Управление шаблонами:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )




@bot.callback_query_handler(func=lambda call: call.data == "admin_services")
def handle_admin_services(call):
    """Handle admin services settings"""
    if not has_access_level(call.from_user.id, ["admin"]):
        bot.answer_callback_query(call.id, "У вас нет доступа к этой функции")
        return

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("📤 Загрузить договор на бит", callback_data="admin_upload_contract"),
        types.InlineKeyboardButton("📝 Управление шаблонами", callback_data="admin_templates"),
        types.InlineKeyboardButton("⚙️ Настройки сервисов", callback_data="admin_service_settings"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
    )

    bot.edit_message_text(
        "⚙️ Управление сервисами и настройками:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )




@bot.callback_query_handler(func=lambda call: call.data.startswith("check_crypto_"))
def handle_crypto_payment_check(call):
    """Check Crypto Bot payment status"""
    invoice_id = call.data.split("_")[2]
    
    try:
        import requests
        
        # Check Crypto Bot invoice status
        crypto_api_url = f"https://pay.crypt.bot/api/getInvoices"
        
        payload = {
            "invoice_ids": invoice_id
        }
        
        headers = {
            "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN,
            "Content-Type": "application/json"
        }
        
        response = requests.post(crypto_api_url, json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("ok") and data["result"]["items"]:
                invoice = data["result"]["items"][0]
                status = invoice.get("status")
                
                if status == "paid":
                    # Payment successful
                    conn = get_pg_connection()
                    if not conn:
                        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
                        return
                    
                    try:
                        cursor = conn.cursor()
                        
                        # Get order info
                        cursor.execute('SELECT user_id, amount FROM orders WHERE payment_id = %s', (invoice_id,))
                        order_info = cursor.fetchone()
                        
                        if order_info:
                            user_id, amount = order_info
                            
                            # Update order status
                            cursor.execute('UPDATE orders SET status = %s WHERE payment_id = %s', ('completed', invoice_id))
                            
                            # Add balance
                            change_user_balance(user_id, amount)
                            
                            conn.commit()
                            
                            bot.edit_message_text(
                                f"✅ Платеж успешно обработан!\n\nВаш баланс пополнен на {amount}₽",
                                call.message.chat.id,
                                call.message.message_id
                            )
                        else:
                            bot.answer_callback_query(call.id, "❌ Заказ не найден", show_alert=True)
                            
                    except Error as e:
                        logger.error(f"DB error processing Crypto Bot payment: {e}")
                        bot.answer_callback_query(call.id, "❌ Ошибка обработки платежа", show_alert=True)
                    finally:
                        if conn:
                            cursor.close()
                            return_pg_connection(conn)
                            
                elif status == "active":
                    bot.answer_callback_query(call.id, "⏳ Платеж еще не поступил", show_alert=True)
                else:
                    bot.answer_callback_query(call.id, f"❌ Статус платежа: {status}", show_alert=True)
            else:
                bot.answer_callback_query(call.id, "❌ Счет не найден", show_alert=True)
        else:
            bot.answer_callback_query(call.id, "❌ Ошибка проверки статуса", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error checking Crypto Bot payment: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка проверки платежа", show_alert=True)




@bot.callback_query_handler(func=lambda call: call.data.startswith("check_stars_"))
def handle_check_stars(call):
    """Check Telegram Stars payment status"""
    payment_id = call.data.split("_")[2]
    
    try:
        # Здесь должна быть логика проверки статуса Stars
        # Пока что просто показываем сообщение о необходимости ручной проверки
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🔄 Проверить снова", callback_data=f"check_stars_{payment_id}"),
            types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_topup")
        )
        
        bot.edit_message_text(
            f"⭐ Проверка оплаты Stars\n\n"
            f"Для проверки статуса оплаты обратитесь к администратору или попробуйте позже.\n"
            f"ID платежа: {payment_id}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error checking Stars payment: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при проверке Stars", show_alert=True)




@bot.callback_query_handler(func=lambda call: call.data.startswith("check_ton_"))
def handle_check_ton(call):
    """Check TON payment status"""
    payment_id = call.data.split("_")[2]
    
    try:
        # Здесь должна быть логика проверки TON транзакций
        # Пока что просто показываем сообщение о необходимости ручной проверки
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🔄 Проверить снова", callback_data=f"check_ton_{payment_id}"),
            types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_topup")
        )
        
        bot.edit_message_text(
            f"💎 Проверка оплаты TON\n\n"
            f"Для проверки статуса оплаты обратитесь к администратору или попробуйте позже.\n"
            f"ID платежа: {payment_id}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error checking TON payment: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при проверке TON", show_alert=True)




@bot.callback_query_handler(func=lambda call: call.data == "back_to_my_releases")
def back_to_my_releases(call):
    """Return to my releases list"""
    # Получаем ID пользователя из колбэка
    user_id = call.from_user.id

    # Показываем релизы
    handle_my_releases(call.message, user_id)

    # Пытаемся удалить предыдущее сообщение (не критично, если не получится)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except Exception as e:
        logger.warning(f"Could not delete message: {e}")




@bot.message_handler(func=lambda message: message.text.startswith("🔍 Подробности релиза: "))
def handle_release_details_request(message):
    """Handle request for release details"""
    try:
        # Извлекаем название релиза из текста кнопки
        release_name = message.text.split(":", 1)[1].strip()
        user_id = message.from_user.id

        conn = get_pg_connection()
        if not conn:
            bot.reply_to(message, "❌ Ошибка подключения к базе данных.")
            return

        cursor = conn.cursor()

        # Ищем релиз по названию и ID пользователя
        cursor.execute('''
            SELECT id, release_type, artist_name, release_name, producer, genre,
                   release_date, performer_name, music_author, explicit_content,
                   yandex_soon, create_links, tiktok_commercial, tiktok_full_version, status, preview_start, upc_code
            FROM releases 
            WHERE user_id = %s AND release_name = %s
        ''', (user_id, release_name))

        release = cursor.fetchone()

        if not release:
            bot.reply_to(message, "❌ Релиз не найден.")
            return

        # Распаковываем данные релиза
        (release_id, release_type, artist_name, release_name, producer, genre,
         release_date, performer_name, music_author, explicit_content,
         yandex_soon, create_links, tiktok_commercial, tiktok_full_version, status, preview_start, upc_code) = release

        # Форматируем информацию о релизе
        tiktok_seconds_text = f"{preview_start} сек" if preview_start else "Не указано"
        details = (
            f"📀 Детали релиза: {release_name}\n\n"
            f"🎵 Тип: {release_type}\n"
            f"🎤 Артист: {artist_name}\n"
            f"🎹 Продюсер: {producer or 'Не указан'}\n"
            f"🎼 Жанр: {genre}\n"
            f"📅 Дата релиза: {release_date.strftime('%d.%m.%Y')}\n"
            f"👤 Исполнитель: {performer_name}\n"
            f"✍️ Автор музыки: {music_author}\n"
            f"🔞 Explicit: {'Да' if explicit_content else 'Нет'}\n"
            f"🟢 Яндекс 'Скоро': {'Да' if yandex_soon else 'Нет'}\n"
            f"🔗 Создать ссылки: {'Да' if create_links else 'Нет'}\n"
            f"📱 TikTok коммерч.: {'Да' if tiktok_commercial else 'Нет'}\n"
            f"🎵 TikTok полная версия: {'Да' if tiktok_full_version else 'Нет'}\n"
            f"⏱️ Секунды TikTok: {tiktok_seconds_text}\n"
            f"🔖 UPC код: {upc_code or 'пока что нет'}\n"
            f"🟢 Статус: {status}"
        )

        # Создаем клавиатуру с действиями
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add(
            types.KeyboardButton("📝 Запросить обновление статуса"),
            types.KeyboardButton("◀️ Назад к моим релизам")
        )

        bot.reply_to(message, details, reply_markup=markup)

    except Exception as e:
        logger.error(f"Error fetching release details: {e}")
        bot.reply_to(message, "❌ Произошла ошибка при получении деталей релиза.")




@bot.message_handler(func=lambda message: message.text == "🎤 Изменить имя артиста")
def edit_artist_name(message):
    """Start editing artist name"""
    bot.reply_to(message, "Введите новое имя артиста:")
    bot.register_next_step_handler(message, save_artist_name)




@bot.message_handler(func=lambda message: message.text == "👥 Изменить ФИО")
def edit_fio(message):
    """Start editing FIO"""
    bot.reply_to(message, "Введите новые ФИО:")
    bot.register_next_step_handler(message, save_fio)




@bot.callback_query_handler(func=lambda call: call.data.startswith("support_detail_"))
def handle_admin_support_detail(call):
    request_id = call.data.split("_", 2)[2]
    show_support_detail(call, request_id)




@bot.callback_query_handler(func=lambda call: call.data == "admin_users")
def handle_admin_users(call):
    """Handle displaying all users in the admin panel"""
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных.", show_alert=True)
        return

    try:
        cursor = conn.cursor()
        cursor.execute('SELECT telegram_id, tg, name FROM label ORDER BY name')
        users = cursor.fetchall()

        if not users:
            message_text = "🤷‍♀️ В базе данных нет зарегистрированных пользователей."
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))
            bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return

        markup = types.InlineKeyboardMarkup(row_width=1)

        for i, (user_id, username, name) in enumerate(users):
            display_name = f"{name} (@{username})" if name and username else f"ID: {user_id}"
            
            # Create a row with user name and action buttons
            markup.row(
                types.InlineKeyboardButton(display_name, callback_data=f"user_info_{user_id}")
            )
            
            # Create a row with two action buttons
            markup.row(
                types.InlineKeyboardButton("🔧 Управление ролью", callback_data=f"user_role_{user_id}"),
                types.InlineKeyboardButton("📊 Запросы отчетов", callback_data=f"user_reports_{user_id}")
            )

            # Row with start distribution on behalf button
            markup.row(
                types.InlineKeyboardButton("🎵 Дистрибуция от имени", callback_data="service_release_for_artist")
            )

        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))
        bot.edit_message_text(
            f"👥 Список пользователей ({len(users)})\n\nВыберите пользователя:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Error in handle_admin_users: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при получении списка пользователей.", show_alert=True)
    finally:
        if conn:
            try:
                cursor.close()
            except Exception:
                pass
            return_pg_connection(conn)


@bot.callback_query_handler(func=lambda call: call.data == "admin_report_requests")
def handle_admin_report_requests(call):
    """Handle admin view of all report requests"""
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Get all report requests with user info
        cursor.execute('''
            SELECT r.id, r.user_id, r.status, r.created_at, r.completed_at, r.request_type,
                r.upc_code,
                   l.name, l.tg
            FROM report_requests r
            JOIN label l ON r.user_id = l.telegram_id
            ORDER BY r.created_at DESC
        ''')
        
        reports = cursor.fetchall()
        
        if not reports:
            message_text = "📊 Запросы отчетов отсутствуют"
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_users"))
            bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=markup)
            return
        
        # Group reports by status
        pending_reports = [r for r in reports if r[2] == 'pending']
        processing_reports = [r for r in reports if r[2] == 'processing']
        completed_reports = [r for r in reports if r[2] == 'completed']
        rejected_reports = [r for r in reports if r[2] == 'rejected']
        
        message_text = "📊 Запросы отчетов\n\n"
        message_text += f"⏳ В ожидании: {len(pending_reports)}\n"
        message_text += f"🔄 В обработке: {len(processing_reports)}\n"
        message_text += f"✅ Завершено: {len(completed_reports)}\n"
        message_text += f"❌ Отклонено: {len(rejected_reports)}\n\n"
        
        # Show pending reports first
        if pending_reports:
            message_text += "🆕 Новые запросы (требуют внимания):\n"
            for report in pending_reports[:5]:  # Show first 5
                report_id, user_id, status, created_at, completed_at, request_type, user_name, username = report
                created_str = created_at.strftime('%d.%m.%Y %H:%M') if created_at else "дата не указана"
                message_text += f"• #{report_id} - {user_name} (@{username}) - {created_str}\n"
            if len(pending_reports) > 5:
                message_text += f"... и еще {len(pending_reports) - 5}\n"
            message_text += "\n"
        
        # Create markup
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        # Add buttons for each status
        if pending_reports:
            markup.add(types.InlineKeyboardButton("⏳ Обработать ожидающие", callback_data="admin_process_pending_reports"))
        
        if processing_reports:
            markup.add(types.InlineKeyboardButton("🔄 В обработке", callback_data="admin_view_processing_reports"))
        
        if completed_reports:
            markup.add(types.InlineKeyboardButton("✅ Завершенные", callback_data="admin_view_completed_reports"))
        
        markup.add(
            types.InlineKeyboardButton("📊 Все отчеты", callback_data="admin_view_all_reports"),
            types.InlineKeyboardButton("◀️ Назад", callback_data="admin_users")
        )
        
        bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        
    except Exception as e:
        logger.error(f"Error in handle_admin_report_requests: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при получении запросов отчетов", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data == "admin_process_pending_reports")
def handle_admin_process_pending_reports(call):
    """Handle admin processing of pending report requests"""
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Get pending reports
        cursor.execute('''
            SELECT r.id, r.user_id, r.created_at, r.request_type,
                r.upc_code,
                   l.name, l.tg
            FROM report_requests r
            JOIN label l ON r.user_id = l.telegram_id
            WHERE r.status = 'pending'
            ORDER BY r.created_at ASC
        ''')
        
        pending_reports = cursor.fetchall()
        
        if not pending_reports:
            bot.answer_callback_query(call.id, "✅ Нет ожидающих отчетов", show_alert=True)
            return
        
        # Show first pending report
        report = pending_reports[0]
        report_id, user_id, created_at, request_type, user_name, username = report
        
        created_str = created_at.strftime('%d.%m.%Y %H:%M') if created_at else "дата не указана"
        
        message_text = f"📊 Обработка отчета #{report_id}\n\n"
        message_text += f"👤 Пользователь: {user_name} (@{username})\n"
        message_text += f"📅 Дата запроса: {created_str}\n"
        message_text += f"📋 Тип запроса: {request_type}\n\n"
        message_text += f"📊 Отчет будет создан в формате XLSX с детальной информацией\n"
        message_text += f"💡 Выберите действие:"
        
        # Create markup
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ Принять в работу", callback_data=f"admin_start_report_{report_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"admin_reject_report_{report_id}")
        )
        
        if len(pending_reports) > 1:
            markup.add(types.InlineKeyboardButton(f"⏭️ Следующий ({len(pending_reports)-1} осталось)", callback_data=f"admin_next_pending_report"))
        
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_report_requests"))
        
        bot.edit_message_text(message_text, call.message.chat.id, call.message.message_id, reply_markup=markup)
        
    except Exception as e:
        logger.error(f"Error in handle_admin_process_pending_reports: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при получении ожидающих отчетов", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_send_report_"))
def handle_admin_send_report(call):
    """Handle admin sending completed report to user"""
    report_id = int(call.data.split("_")[3])
    
    try:
        # Get report and user info
        conn = get_pg_connection()
        if not conn:
            bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных")
            return
        
        cursor = conn.cursor()
        
        # Get report info
        cursor.execute('''
            SELECT r.user_id, r.request_type, l.name, l.tg
            FROM report_requests r
            JOIN label l ON r.user_id = l.telegram_id
            WHERE r.id = %s
        ''', (report_id,))
        
        report_info = cursor.fetchone()
        if not report_info:
            bot.answer_callback_query(call.id, "❌ Отчет не найден")
            return
        
        user_id, request_type, user_name, username = report_info
        
        # Get user data for report
        cursor.execute('''
            SELECT telegram_id, name, tg, email, created_at, status, role
            FROM label 
            WHERE telegram_id = %s
        ''', (user_id,))
        
        user_data = cursor.fetchone()
        if not user_data:
            bot.answer_callback_query(call.id, "❌ Данные пользователя не найдены")
            return
        
        # Get user releases
        cursor.execute('''
            SELECT id, name, type, status, created_at, updated_at, description
            FROM releases 
            WHERE user_id = %s
            ORDER BY created_at DESC
        ''', (user_id,))
        
        releases_data = cursor.fetchall()
        
        # Convert to list of dictionaries
        releases_list = []
        for release in releases_data:
            releases_list.append({
                'id': release[0],
                'name': release[1],
                'type': release[2],
                'status': release[3],
                'created_at': release[4],
                'updated_at': release[5],
                'description': release[6],
                'track_count': 0  # Можно добавить подсчет треков если нужно
            })
        
        # Create Excel report
        if not XLSX_AVAILABLE:
            bot.answer_callback_query(call.id, "❌ Модуль Excel недоступен")
            return
        
        # Convert user data to dictionary
        user_dict = {
            'telegram_id': user_data[0],
            'name': user_data[1],
            'tg': user_data[2],
            'email': user_data[3],
            'created_at': user_data[4],
            'status': user_data[5],
            'role': user_data[6]
        }
        
        # Get additional data for detailed report
        # Get promo codes data
        cursor.execute('''
            SELECT id, code, amount, max_uses, current_uses, expires_at, is_active
            FROM promo_codes 
            WHERE user_id = %s
            ORDER BY created_at DESC
        ''', (user_id,))
        
        promo_codes_data = cursor.fetchall()
        promo_codes_list = []
        for promo in promo_codes_data:
            promo_codes_list.append({
                'id': promo[0],
                'code': promo[1],
                'amount': promo[2],
                'max_uses': promo[3],
                'current_uses': promo[4],
                'expires_at': promo[5],
                'is_active': promo[6]
            })
        
        # Get orders data
        cursor.execute('''
            SELECT id, service_type, status, amount, created_at, completed_at, description
            FROM orders 
            WHERE user_id = %s
            ORDER BY created_at DESC
        ''', (user_id,))
        
        orders_data = cursor.fetchall()
        orders_list = []
        for order in orders_data:
            orders_list.append({
                'id': order[0],
                'service_type': order[1],
                'status': order[2],
                'amount': order[3],
                'created_at': order[4],
                'completed_at': order[5],
                'description': order[6]
            })
        
        # Generate detailed XLSX report
        wb = create_detailed_xlsx_report(user_dict, releases_list, promo_codes_list, orders_list)
        
        # Update report status
        cursor.execute('''
            UPDATE report_requests 
            SET status = 'completed', 
                completed_at = NOW(),
                admin_id = %s
            WHERE id = %s
        ''', (call.from_user.id, report_id))
        
        conn.commit()
        
        # Send XLSX report to user
        try:
            filename = f"Отчет_{user_name}_{datetime.now().strftime('%d%m%Y')}.xlsx"
            if send_xlsx_report(user_id, wb, filename):
                # Notify admin
                bot.edit_message_text(
                    f"✅ Отчет #{report_id} успешно отправлен пользователю {user_name} (@{username or 'без username'})\n\n"
                    f"📊 Тип отчета: {request_type}\n"
                    f"📅 Дата отправки: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                    f"📎 Отчет отправлен в формате XLSX с детальной информацией\n"
                    f"📋 Содержит {len(wb.worksheets)} листов с данными",
                    call.message.chat.id,
                    call.message.message_id,
                    reply_markup=types.InlineKeyboardMarkup().add(
                        types.InlineKeyboardButton("◀️ Назад к запросам", callback_data="admin_report_requests")
                    )
                )
            else:
                bot.answer_callback_query(call.id, "❌ Ошибка при отправке отчета")
            
        except Exception as e:
            logger.error(f"Error sending report to user: {e}")
            bot.answer_callback_query(call.id, f"❌ Ошибка отправки отчета: {str(e)}")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error in handle_admin_send_report: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}")




@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_reject_report_"))
def handle_admin_reject_report(call):
    """Handle admin rejecting a report request"""
    report_id = int(call.data.split("_")[3])
    
    # Store report_id in bot.user_data for rejection reason
    admin_id = call.from_user.id
    bot.user_data[admin_id] = {'report_id': report_id, 'action': 'reject_report'}
    
    bot.edit_message_text(
        f"❌ Отклонение отчета #{report_id}\n\n"
        f"📝 Укажите причину отклонения:\n\n"
        f"💡 Примеры причин:\n"
        f"• Недостаточно данных для составления отчета\n"
        f"• Нарушение правил использования сервиса\n"
        f"• Технические проблемы\n\n"
        f"❌ Для отмены нажмите 'Отмена'",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("❌ Отмена", callback_data="admin_report_requests")
        )
    )
    
    # Register handler for rejection reason
    bot.register_next_step_handler(call.message, handle_admin_report_rejection_reason)




@bot.callback_query_handler(func=lambda call: call.data.startswith("download_report_"))
def handle_download_report(call):
    """Handle user downloading a completed report"""
    report_id = int(call.data.split("_")[2])
    user_id = call.from_user.id
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Get report info
        cursor.execute('''
            SELECT report_file_id, status
            FROM report_requests 
            WHERE id = %s AND user_id = %s
        ''', (report_id, user_id))
        
        report = cursor.fetchone()
        if not report:
            bot.answer_callback_query(call.id, "❌ Отчет не найден", show_alert=True)
            return
        
        report_file_id, status = report
        
        if status != 'completed':
            bot.answer_callback_query(call.id, "❌ Отчет еще не готов", show_alert=True)
            return
        
        if not report_file_id:
            bot.answer_callback_query(call.id, "❌ Файл отчета не найден", show_alert=True)
            return
        
        # Send the report file
        try:
            bot.send_document(
                call.message.chat.id,
                report_file_id,
                caption=f"📊 Отчет #{report_id}\n\n"
                f"✅ Ваш отчет готов к использованию!\n"
                f"📅 Дата скачивания: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
                f"💡 Если у вас есть вопросы по отчету, обратитесь к администратору."
            )
            
            bot.answer_callback_query(call.id, "✅ Отчет отправлен!")
            
        except Exception as e:
            logger.error(f"Error sending report file {report_id}: {e}")
            bot.answer_callback_query(call.id, "❌ Ошибка при отправке файла", show_alert=True)
        
    except Exception as e:
        logger.error(f"Error downloading report {report_id}: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при получении отчета", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("user_role_"))
def handle_user_role_management(call):
    """Handle user role management"""
    user_id = int(call.data.split("_")[2])
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Get current user roles
        cursor.execute('SELECT name, tg, admin, artist, owner, creator FROM label WHERE telegram_id = %s', (user_id,))
        user_info = cursor.fetchone()
        
        if not user_info:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден", show_alert=True)
            return
        
        name, username, admin_status, artist_status, owner_status, creator_status = user_info
        
        # Create role management menu
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        # Admin role toggle
        admin_text = "✅ Администратор" if admin_status else "❌ Администратор"
        markup.add(types.InlineKeyboardButton(
            admin_text, 
            callback_data=f"toggle_admin_{user_id}"
        ))
        
        # Artist role toggle
        artist_text = "✅ Артист" if artist_status else "❌ Артист"
        markup.add(types.InlineKeyboardButton(
            artist_text, 
            callback_data=f"toggle_artist_{user_id}"
        ))
        
        # Owner role toggle
        owner_text = "✅ Owner" if owner_status else "❌ Owner"
        markup.add(types.InlineKeyboardButton(
            owner_text, 
            callback_data=f"toggle_owner_{user_id}"
        ))
        

        
        # Creator role toggle
        creator_text = "✅ Creator" if creator_status else "❌ Creator"
        markup.add(types.InlineKeyboardButton(
            creator_text, 
            callback_data=f"toggle_creator_{user_id}"
        ))
        
        # Back buttons
        markup.add(types.InlineKeyboardButton("◀️ К списку пользователей", callback_data="admin_users"))
        markup.add(types.InlineKeyboardButton("◀️ В админ панель", callback_data="admin_back"))
        
        display_name = f"{name} (@{username})" if name and username else f"ID: {user_id}"
        
        bot.edit_message_text(
            f"🔧 Управление ролями пользователя\n\n"
            f"Пользователь: {display_name}\n"
            f"Текущие роли:\n"
            f"• Администратор: {'Да' if admin_status else 'Нет'}\n"
            f"• Артист: {'Да' if artist_status else 'Нет'}\n"
            f"• Owner: {'Да' if owner_status else 'Нет'}\n"
            f"• Creator: {'Да' if creator_status else 'Нет'}\n\n"
            f"Нажмите на роль для изменения:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error in user role management: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_artist_"))
def handle_toggle_artist_role(call):
    """Toggle artist role for user"""
    user_id = int(call.data.split("_")[2])
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Get current artist status
        cursor.execute('SELECT artist, name, tg FROM label WHERE telegram_id = %s', (user_id,))
        user_info = cursor.fetchone()
        
        if not user_info:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден", show_alert=True)
            return
        
        current_artist, name, username = user_info
        new_artist = 0 if current_artist else 1
        
        # Update artist status
        cursor.execute('UPDATE label SET artist = %s WHERE telegram_id = %s', (new_artist, user_id))
        conn.commit()
        
        display_name = f"{name} (@{username})" if name and username else f"ID: {user_id}"
        status_text = "назначен артистом" if new_artist else "снят с артиста"
        
        bot.answer_callback_query(
            call.id, 
            f"✅ {display_name} {status_text}", 
            show_alert=True
        )
        
        # Refresh the role management menu
        return handle_user_role_management(call)
        
    except Exception as e:
        logger.error(f"Error toggling artist role: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_steezy_"))
def handle_toggle_steezy_role(call):
    """Toggle steezy role for user"""
    user_id = int(call.data.split("_")[2])
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Get current steezy status
        cursor.execute('SELECT steezy, name, tg FROM label WHERE telegram_id = %s', (user_id,))
        user_info = cursor.fetchone()
        
        if not user_info:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден", show_alert=True)
            return
        
        current_steezy, name, username = user_info
        new_steezy = 0 if current_steezy else 1
        
        # Update steezy status
        cursor.execute('UPDATE label SET steezy = %s WHERE telegram_id = %s', (new_steezy, user_id))
        conn.commit()
        
        display_name = f"{name} (@{username})" if name and username else f"ID: {user_id}"
        status_text = "назначен Steezy" if new_steezy else "снят с Steezy"
        
        bot.answer_callback_query(
            call.id, 
            f"✅ {display_name} {status_text}", 
            show_alert=True
        )
        
        # Refresh the role management menu
        handle_user_role_management(call)
        
    except Exception as e:
        logger.error(f"Error toggling steezy role: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle_shvepz_"))
def handle_toggle_shvepz_role(call):
    """Toggle shvepz role for user"""
    user_id = int(call.data.split("_")[2])
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Get current shvepz status
        cursor.execute('SELECT shvepz, name, tg FROM label WHERE telegram_id = %s', (user_id,))
        user_info = cursor.fetchone()
        
        if not user_info:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден", show_alert=True)
            return
        
        current_shvepz, name, username = user_info
        new_shvepz = 0 if current_shvepz else 1
        
        # Update shvepz status
        cursor.execute('UPDATE label SET shvepz = %s WHERE telegram_id = %s', (new_shvepz, user_id))
        conn.commit()
        
        display_name = f"{name} (@{username})" if name and username else f"ID: {user_id}"
        status_text = "назначен Shvepz" if new_shvepz else "снят с Shvepz"
        
        bot.answer_callback_query(
            call.id, 
            f"✅ {display_name} {status_text}", 
            show_alert=True
        )
        
        # Refresh the role management menu
        handle_user_role_management(call)
        
    except Exception as e:
        logger.error(f"Error toggling shvepz role: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("user_reports_"))
def handle_user_reports(call):
    """Handle user report requests"""
    user_id = int(call.data.split("_")[2])
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Get user info
        cursor.execute('SELECT name, tg FROM label WHERE telegram_id = %s', (user_id,))
        user_info = cursor.fetchone()
        
        if not user_info:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден", show_alert=True)
            return
        
        name, username = user_info
        
        # Get report requests for this user
        cursor.execute('''
            SELECT id, release_type, request_type, status, created_at, notes 
            FROM report_requests 
            WHERE user_id = %s 
            ORDER BY created_at DESC
        ''', (user_id,))
        
        reports = cursor.fetchall()
        
        if not reports:
            message_text = f"📊 Запросы отчетов пользователя {name} (@{username})\n\n❌ У пользователя нет запросов отчетов"
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("◀️ К списку пользователей", callback_data="admin_users"))
            markup.add(types.InlineKeyboardButton("◀️ В админ панель", callback_data="admin_back"))
            
            bot.edit_message_text(
                message_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            return
        
        # Format reports list
        display_name = f"{name} (@{username})" if name and username else f"ID: {user_id}"
        
        reports_text = f"📊 Запросы отчетов пользователя {display_name}\n\n"
        
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for report_id, release_type, request_type, status, created_at, notes in reports:
            status_emoji = {
                'pending': '⏳',
                'processing': '🔄',
                'completed': '✅',
                'rejected': '❌'
            }.get(status, '❓')
            
            date_str = created_at.strftime('%d.%m.%Y %H:%M') if created_at else 'Не указана'
            
            reports_text += (
                f"{status_emoji} <b>{request_type}</b> - {release_type}\n"
                f"📅 {date_str}\n"
                f"📝 Статус: {status}\n"
            )
            
            if notes:
                reports_text += f"💬 {notes}\n"
            
            reports_text += "\n"
            
            # Add button to view/edit report
            markup.add(types.InlineKeyboardButton(
                f"📋 {request_type} - {release_type} ({status})",
                callback_data=f"view_report_{report_id}"
            ))
        
        # Add back buttons
        markup.add(types.InlineKeyboardButton("◀️ К списку пользователей", callback_data="admin_users"))
        markup.add(types.InlineKeyboardButton("◀️ В админ панель", callback_data="admin_back"))
        
        bot.edit_message_text(
            reports_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
        
    except Exception as e:
        logger.error(f"Error showing user reports: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.endswith("_admin"))
def handle_admin_release_details(call):
    """Handle release details in admin mode"""
    logger.info(f"handle_admin_release_details called with callback_data: {call.data}")
    if call.data.startswith("album_detail_"):
        album_id = int(call.data.split("_")[2])
        logger.info(f"Processing album_detail_ with album_id: {album_id}")
        show_album_details(call, album_id, admin_mode=True)
    elif call.data.startswith("my_release_detail_"):
        release_id = int(call.data.split("_")[3])
        logger.info(f"Processing my_release_detail_ with release_id: {release_id}")
        show_my_release_details(call, release_id, admin_mode=True)




@bot.callback_query_handler(func=lambda call: call.data.startswith("album_upc_update_"))
def handle_album_upc_update(call):
    """Handle album UPC code update request"""
    try:
        parts = call.data.split("_")
        album_id = int(parts[3])
        
        # Check admin access
        if not has_access_level(call.from_user.id, ["admin"]):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут изменять UPC код", show_alert=True)
            return
        
        # Get current UPC code
        conn = get_pg_connection()
        if not conn:
            bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
            return
        
        cursor = conn.cursor()
        cursor.execute('SELECT upc_code FROM releases WHERE id = %s', (album_id,))
        result = cursor.fetchone()
        current_upc = result[0] if result else "пока что нет"
        
        # Create back button
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "◀️ Назад к альбому",
            callback_data=f"album_detail_{album_id}_admin"
        ))
        
        bot.edit_message_text(
            f"🏷️ Текущий UPC код альбома: {current_upc}\n\n"
            "Введите новый UPC код для альбома:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
        # Register next step handler
        bot.register_next_step_handler(call.message, process_album_upc_update, album_id)
        
    except Exception as e:
        logger.error(f"Error in handle_album_upc_update: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)




@bot.callback_query_handler(func=lambda call: call.data.startswith("change_upc_"))
def handle_change_upc_request(call):
    """Handle UPC code change request (admin only)"""
    # Проверяем права администратора
    if not has_access_level(call.from_user.id, ["admin"]):
        bot.answer_callback_query(
            call.id,
            "❌ Только администраторы могут изменять UPC-код",
            show_alert=True
        )
        return

    release_id = call.data.split("_")[2]
    bot.edit_message_text(
        "✏️ Введите новый UPC код для релиза:",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(call.message, process_upc_update, release_id)




@bot.callback_query_handler(func=lambda call: call.data.startswith("manage_platform_links_"))
def handle_manage_platform_links_request(call):
    """Handle platform links management request (admin only)"""
    # Проверяем права администратора
    if not has_access_level(call.from_user.id, ["admin"]):
        bot.answer_callback_query(
            call.id,
            "❌ Только администраторы могут управлять информацией о площадках",
            show_alert=True
        )
        return

    release_id = call.data.split("_")[3]
    
    # Определяем правильный callback для кнопки "Назад"
    back_callback = get_back_callback_for_release(release_id)
    back_text = "◀️ Назад к альбому" if "album_detail" in back_callback else "◀️ Назад к релизу"
    
    # Показываем меню управления ссылками
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Добавить информацию", callback_data=f"add_platform_link_{release_id}"),
        types.InlineKeyboardButton("📝 Редактировать информацию", callback_data=f"edit_platform_links_{release_id}"),
        types.InlineKeyboardButton("❌ Удалить информацию", callback_data=f"delete_platform_links_{release_id}"),
        types.InlineKeyboardButton("👁️ Просмотреть информацию", callback_data=f"view_platform_links_{release_id}"),
        types.InlineKeyboardButton(back_text, callback_data=back_callback)
    )
    
    bot.edit_message_text(
        "🔗 Управление ссылками\n\n"
        "Выберите действие:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )




@bot.callback_query_handler(func=lambda call: call.data.startswith("quick_link_menu_"))
def handle_quick_link_menu(call):
    """Prompt admin to send new platform link directly"""
    if not has_access_level(call.from_user.id, ["admin"]):
        bot.answer_callback_query(call.id, "❌ Недостаточно прав", show_alert=True)
        return

    release_id = call.data.split("_")[-1]
    bot.answer_callback_query(call.id, "✏️ Отправьте новую ссылку сообщением")
    prompt_new_platform_link_input(call.message.chat.id, release_id)




@bot.callback_query_handler(func=lambda call: call.data.startswith("view_platform_links_"))
def handle_view_platform_links_request(call):
    """Handle view platform links request"""
    release_id = call.data.split("_")[3]
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute('SELECT platform_links FROM releases WHERE id = %s', (release_id,))
        result = cursor.fetchone()
        
        if result and result[0] and result[0] != '{}':
            platform_links = result[0]
            if isinstance(platform_links, str):
                platform_links = json.loads(platform_links)
            
            links_text = "🔗 Добавленная информация:\n\n"
            for platform, url in platform_links.items():
                links_text += f"📱 {platform}: {url}\n"
        else:
            links_text = "🔗 Информация не добавлена"
        
        # Определяем правильный callback для кнопки "Назад"
        back_callback = get_back_callback_for_release(release_id)
        back_text = "◀️ Назад к альбому" if "album_detail" in back_callback else "◀️ Назад к релизу"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                back_text,
                callback_data=back_callback
            )
        )
        
        bot.edit_message_text(
            links_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error viewing platform information: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_platform_"))
def handle_edit_specific_platform_request(call):
    """Handle edit specific platform link request"""
    parts = call.data.split("_")
    release_id = parts[2]
    platform_name = parts[3]
    
    bot.edit_message_text(
        f"✏️ Редактирование информации: {platform_name}\n\n"
        "Введите новую информацию в любом формате:\n"
        "• Текст\n"
        "• Ссылки\n"
        "• Многострочный текст\n"
        "• Любые символы и эмодзи 🎵🎤🎹",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(call.message, process_edit_platform_link, release_id, platform_name)




@bot.callback_query_handler(func=lambda call: call.data.startswith("delete_platform_links_"))
def handle_delete_platform_links_request(call):
    """Handle delete platform links request"""
    release_id = call.data.split("_")[3]
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Очищаем всю информацию
        cursor.execute(
            'UPDATE releases SET platform_links = %s WHERE id = %s',
            ('{}', release_id)
        )
        conn.commit()
        
        # Определяем правильный callback для кнопки "Назад"
        back_callback = get_back_callback_for_release(release_id)
        back_text = "◀️ Назад к альбому" if "album_detail" in back_callback else "◀️ Назад к релизу"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton(
                back_text,
                callback_data=back_callback
            )
        )
        
        bot.edit_message_text(
            "✅ Вся информация удалена!",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error deleting platform information: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("user_detail_"))
def show_user_detail(call):
    """Show detailed information about user and their releases"""
    user_id = int(call.data.split("_")[2])

    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return

    try:
        cursor = conn.cursor()

        # Get user info
        cursor.execute('''
            SELECT name, tg, kanal, fio, role, created_date 
            FROM label 
            WHERE telegram_id = %s
        ''', (user_id,))
        user_info = cursor.fetchone()

        if not user_info:
            bot.answer_callback_query(call.id, "❌ Пользователь не найден", show_alert=True)
            return

        name, username, channel, fio, role, created_date = user_info

        # Get user's releases
        cursor.execute('''
            SELECT id, release_name, release_date, status 
            FROM releases 
            WHERE user_id = %s
            ORDER BY release_date DESC
        ''', (user_id,))
        releases = cursor.fetchall()

        # Format user info
        user_text = (
            f"👤 Информация о пользователе:\n\n"
            f"🎤 Имя: {name or 'Не указано'}\n"
            f"📱 Username: @{username or 'Не указан'}\n"
            f"📺 Канал: {channel or 'Не указан'}\n"
            f"👥 ФИО: {fio or 'Не указано'}\n"
            f"🔑 Роль: {role or 'Не указана'}\n"
            f"📅 Дата регистрации: {created_date.strftime('%d.%m.%Y') if created_date else 'Неизвестно'}\n\n"
            f"📀 Всего релизов: {len(releases)}"
        )

        markup = types.InlineKeyboardMarkup(row_width=1)

        # Add buttons for each release
        for release_id, release_name, release_date, status in releases:
            btn_text = f"{release_name} ({release_date.strftime('%d.%m.%Y') if release_date else 'нет даты'}) - {status}"
            markup.add(types.InlineKeyboardButton(
                btn_text,
                callback_data=f"my_release_detail_{release_id}_admin"  # Добавлен суффикс _admin
            ))

        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_users"))

        bot.edit_message_text(
            user_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

    except Error as e:
        logger.error(f"PostgreSQL error in show_user_detail: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.message_handler(commands=['код', 'webauth'])
def handle_web_auth_code(message):
    """Генерация кода для веб-авторизации"""
    user_id = message.from_user.id
    username = message.from_user.username or f"user_{user_id}"
    
    try:
        # Генерируем 6-значный код
        auth_code = str(random.randint(100000, 999999))
        
        # Подключаемся к базе данных
        conn = get_pg_connection()
        if not conn:
            bot.reply_to(message, "❌ Ошибка подключения к базе данных")
            return
            
        cursor = conn.cursor()
        
        # Проверяем существование таблицы auth_codes
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'auth_codes'
            )
        """)
        table_exists = cursor.fetchone()[0]
        
        if not table_exists:
            # Создаем таблицу auth_codes
            cursor.execute("""
                CREATE TABLE auth_codes (
                    id SERIAL PRIMARY KEY,
                    code VARCHAR(6) UNIQUE NOT NULL,
                    user_id BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    used BOOLEAN DEFAULT FALSE,
                    used_at TIMESTAMP NULL
                )
            """)
            logger.info("Таблица auth_codes создана")
        
        # Удаляем старые неиспользованные коды этого пользователя
        cursor.execute("""
            DELETE FROM auth_codes 
            WHERE user_id = %s AND used = FALSE
        """, (user_id,))
        
        # Вычисляем время истечения (5 минут)
        expires_at = datetime.now() + timedelta(minutes=5)
        
        # Сохраняем новый код
        cursor.execute("""
            INSERT INTO auth_codes (code, user_id, expires_at)
            VALUES (%s, %s, %s)
        """, (auth_code, user_id, expires_at))
        
        conn.commit()
        
        # Отправляем ответ пользователю с кнопкой Web App
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(
            "🌐 Открыть приложение",
            web_app=types.WebAppInfo(url=f"{WEB_APP_URL}?tgid={user_id}")
        ))
        
        bot.reply_to(
            message,
            f"🔐 **Код для веб-авторизации:**\n\n"
            f"**`{auth_code}`**\n\n"
            f"⏰ Код действителен 5 минут\n"
            f"🌐 Нажмите кнопку ниже для автоматического входа\n\n"
            f"🔗 Сайт: {WEB_APP_URL}",
            parse_mode='Markdown',
            reply_markup=markup
        )
        
        logger.info(f"Сгенерирован код веб-авторизации {auth_code} для пользователя {user_id} (@{username})")
        
    except Exception as e:
        logger.error(f"Ошибка генерации кода веб-авторизации: {e}")
        bot.reply_to(message, f"❌ Ошибка генерации кода: {str(e)}")
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)



@bot.message_handler(commands=['test_cover'])
def test_cover_command(message):
    """Команда /test_cover для проверки данных пользователя"""
    user_id = message.from_user.id
    debug_user_data(user_id, "test_cover_command")

    user_data = bot.user_data.get(user_id, {})
    cover_file_id = user_data.get('cover_file_id')

    if cover_file_id:
        bot.send_message(
            message.chat.id,
            f"✅ Cover file ID найден: {cover_file_id}\n\n"
            f"Все ключи в user_data: {list(user_data.keys())}"
        )
    else:
        bot.send_message(
            message.chat.id,
            f"❌ Cover file ID не найден!\n\n"
            f"Все ключи в user_data: {list(user_data.keys())}"
        )




@bot.callback_query_handler(func=lambda call: call.data.startswith("request_report_"))
def handle_report_request(call):
    """Handle report request from user"""
    try:
        parts = call.data.split("_")
        if len(parts) >= 4:
            report_type = parts[2]  # album, single, etc.
            release_id = int(parts[3])
            
            conn = get_pg_connection()
            if not conn:
                bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
                return
            
            try:
                cursor = conn.cursor()
                
                # Get release info
                cursor.execute('''
                    SELECT release_name, release_type, user_id 
                    FROM releases 
                    WHERE id = %s AND user_id = %s
                ''', (release_id, call.from_user.id))
                
                release_info = cursor.fetchone()
                
                if not release_info:
                    bot.answer_callback_query(call.id, "❌ Релиз не найден", show_alert=True)
                    return
                
                release_name, release_type, user_id = release_info
                
                # Check if report request already exists
                cursor.execute('''
                    SELECT id FROM report_requests 
                    WHERE user_id = %s AND release_id = %s AND status = 'pending'
                ''', (user_id, release_id))
                
                if cursor.fetchone():
                    bot.answer_callback_query(call.id, "❌ Запрос отчета уже существует", show_alert=True)
                    return
                
                # Create new report request
                cursor.execute('''
                    INSERT INTO report_requests (user_id, release_id, release_type, request_type, status)
                    VALUES (%s, %s, %s, %s, 'pending')
                ''', (user_id, release_id, release_type, f"Отчет по {report_type}"))
                
                conn.commit()
                
                # Notify all admins with quick access buttons
                admin_ids = get_all_admins()
                for admin_id in admin_ids:
                    try:
                        markup = types.InlineKeyboardMarkup()
                        markup.add(
                            types.InlineKeyboardButton("👥 Пользователи", callback_data="admin_users"),
                            types.InlineKeyboardButton("📊 Запросы отчетов", callback_data="admin_report_requests")
                        )
                        
                        bot.send_message(
                            admin_id,
                            f"📊 Новый запрос отчета!\n\n"
                            f"👤 Пользователь: @{call.from_user.username or 'без username'}\n"
                            f"📀 Релиз: {release_name}\n"
                            f"🎵 Тип: {release_type}\n"
                            f"📋 Запрос: Отчет по {report_type}\n\n"
                            f"💡 Используйте кнопки ниже для быстрого доступа:",
                            reply_markup=markup
                        )
                    except Exception as e:
                        logger.error(f"Failed to notify admin {admin_id}: {e}")
                
                bot.answer_callback_query(
                    call.id, 
                    "✅ Запрос отчета отправлен администраторам!", 
                    show_alert=True
                )
                
                # Return to reports menu
                markup = types.InlineKeyboardMarkup()
                markup.add(
                    types.InlineKeyboardButton("📊 Запросить новый отчет", callback_data="request_new_report"),
                    types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile")
                )
                
                try:
                    bot.edit_message_text(
                        "✅ Запрос отчета отправлен администраторам!\n\nОжидайте уведомления о готовности отчета.",
                        call.message.chat.id,
                        call.message.message_id,
                        reply_markup=markup
                    )
                except Exception:
                    # If edit fails, send new message
                    bot.send_message(
                        call.message.chat.id,
                        "✅ Запрос отчета отправлен администраторам!\n\nОжидайте уведомления о готовности отчета.",
                        reply_markup=markup
                    )
                
            except Exception as e:
                logger.error(f"Error creating report request: {e}")
                bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
            finally:
                if conn:
                    cursor.close()
                    return_pg_connection(conn)
                    
    except Exception as e:
        logger.error(f"Error in report request handler: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)




@bot.callback_query_handler(func=lambda call: call.data == "admin_contracts")
def handle_admin_contracts(call):
    """Handle admin contracts management panel"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Только администраторы могут управлять договорами", show_alert=True)
        return
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Get all contracts
        cursor.execute('''
            SELECT 
                c.id, c.user_id, c.contract_number, c.contract_type, c.status, 
                c.created_at, c.completed_at, c.contract_file_id,
                l.name, l.tg
            FROM contracts c
            JOIN label l ON c.user_id = l.telegram_id
            ORDER BY c.created_at DESC
        ''')
        
        contracts = cursor.fetchall()
        
        if not contracts:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_users"))
            
            bot.edit_message_text(
                "📋 Управление договорами\n\n❌ Нет активных договоров",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
            return
        
        # Create contract list
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        for contract in contracts:
            contract_id, user_id, contract_number, contract_type, status, created_at, completed_at, contract_file_id, user_name, username = contract
            
            # Format dates
            created_str = created_at.strftime('%d.%m.%Y %H:%M') if created_at else "дата не указана"
            
            # Status emoji and text
            status_emoji = {
                'pending': '⏳',
                'processing': '🔄',
                'completed': '✅',
                'rejected': '❌'
            }.get(status, '❓')
            
            # Create button text
            btn_text = f"{status_emoji} {user_name} - {contract_number} ({created_str})"
            
            markup.add(types.InlineKeyboardButton(
                btn_text,
                callback_data=f"admin_view_contract_{contract_id}"
            ))
        
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_users"))
        
        bot.edit_message_text(
            f"📋 Управление договорами ({len(contracts)})\n\n"
            f"📋 Список всех договоров:\n"
            f"⏳ Ожидающие обработки\n"
            f"🔄 В процессе\n"
            f"✅ Завершенные\n"
            f"❌ Отклоненные\n\n"
            f"Выберите договор для просмотра:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error in admin contracts: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при получении договоров", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_view_report_"))
def handle_admin_view_report(call):
    """Handle admin viewing specific report request"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Только администраторы могут просматривать отчеты", show_alert=True)
        return
    
    report_id = int(call.data.split("_")[3])
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Get report details
        cursor.execute('''
            SELECT 
                rr.user_id, rr.release_id, rr.release_type, rr.request_type, 
                rr.status, rr.created_at, rr.completed_at, rr.report_file_id,
                r.upc_code,
                l.name, l.tg, r.release_name, r.artist_name
            FROM report_requests rr
            JOIN label l ON rr.user_id = l.telegram_id
            JOIN releases r ON rr.release_id = r.id
            WHERE rr.id = %s
        ''', (report_id,))
        
        report = cursor.fetchone()
        if not report:
            bot.answer_callback_query(call.id, "❌ Отчет не найден", show_alert=True)
            return
        
        user_id, release_id, release_type, request_type, status, created_at, completed_at, report_file_id, user_name, username, release_name, artist_name = report
        
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
        
        # Create report info text
        report_text = (
            f"📊 Детали запроса отчета #{report_id}\n\n"
            f"👤 Пользователь: {user_name} (@{username})\n"
            f"📀 Релиз: {release_name}\n"
            f"🎵 Тип: {release_type}\n"
            f"📋 Запрос: {request_type}\n"
            f"📅 Создан: {created_str}\n"
            f"✅ Завершен: {completed_str}\n"
            f"🔄 Статус: {status_emoji} {status}\n"
        )
        
        if report_file_id:
            report_text += f"📎 Файл отчета: Прикреплен\n"
        else:
            report_text += f"📎 Файл отчета: Не прикреплен\n"
        
        # Create markup based on status
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        if status == 'pending':
            markup.add(
                types.InlineKeyboardButton("🔄 Взять в работу", callback_data=f"start_report_{report_id}"),
                types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_report_{report_id}")
            )
        elif status == 'processing':
            markup.add(
                types.InlineKeyboardButton("📎 Прикрепить XLSX отчет", callback_data=f"attach_xlsx_report_{report_id}"),
                types.InlineKeyboardButton("✅ Завершить", callback_data=f"complete_report_{report_id}")
            )
        elif status == 'completed':
            markup.add(
                types.InlineKeyboardButton("📎 Просмотреть отчет", callback_data=f"view_report_file_{report_id}"),
                types.InlineKeyboardButton("🔄 Переоткрыть", callback_data=f"reopen_report_{report_id}")
            )
        
        markup.add(
            types.InlineKeyboardButton("👥 К списку пользователей", callback_data="admin_users"),
            types.InlineKeyboardButton("📊 К запросам отчетов", callback_data="admin_report_requests"),
            types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back")
        )
        
        bot.edit_message_text(
            report_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error viewing report {report_id}: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при просмотре отчета", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("reject_report_"))
def handle_reject_report(call):
    """Handle rejecting report"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Только администраторы могут управлять отчетами", show_alert=True)
        return
    
    report_id = int(call.data.split("_")[2])
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute('UPDATE report_requests SET status = %s WHERE id = %s', ('rejected', report_id))
        conn.commit()
        
        bot.answer_callback_query(call.id, "❌ Отчет отклонен", show_alert=True)
        
        # Refresh the report view
        call.data = f"admin_view_report_{report_id}"
        handle_admin_view_report(call)
        
    except Exception as e:
        logger.error(f"Error rejecting report {report_id}: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при изменении статуса", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("complete_report_"))
def handle_complete_report(call):
    """Handle completing report"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Только администраторы могут завершать отчеты", show_alert=True)
        return
    
    report_id = int(call.data.split("_")[2])
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Check if report file is attached
        cursor.execute('SELECT report_file_id, user_id FROM report_requests WHERE id = %s', (report_id,))
        result = cursor.fetchone()
        
        if not result:
            bot.answer_callback_query(call.id, "❌ Отчет не найден", show_alert=True)
            return
        
        report_file_id, user_id = result
        
        if not report_file_id:
            bot.answer_callback_query(call.id, "❌ Сначала прикрепите файл отчета", show_alert=True)
            return
        
        # Update status and completion date
        cursor.execute(
            'UPDATE report_requests SET status = %s, completed_at = %s WHERE id = %s',
            ('completed', datetime.now(), report_id)
        )
        conn.commit()
        
        # Notify user
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📊 Мои отчеты", callback_data="my_reports"))
            
            bot.send_message(
                user_id,
                f"✅ Ваш отчет готов!\n\n"
                f"📊 Отчет #{report_id} был завершен администратором.\n"
                f"📎 Файл отчета прикреплен\n\n"
                f"Просмотрите отчет в разделе 'Мои отчеты'",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")
        
        bot.answer_callback_query(call.id, "✅ Отчет завершен", show_alert=True)
        
        # Refresh the report view
        call.data = f"admin_view_report_{report_id}"
        handle_admin_view_report(call)
        
    except Exception as e:
        logger.error(f"Error completing report {report_id}: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при завершении отчета", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("attach_xlsx_report_"))
def handle_attach_xlsx_report(call):
    """Handle XLSX report file attachment request"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Только администраторы могут прикреплять отчеты", show_alert=True)
        return
    
    report_id = int(call.data.split("_")[3])
    
    # Store report_id in user data for file handling
    bot.user_data[call.from_user.id] = {'attaching_xlsx_report': report_id}
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data=f"admin_view_report_{report_id}"))
    
    bot.edit_message_text(
        f"📎 Прикрепление XLSX отчета #{report_id}\n\n"
        f"📊 Отправьте готовый файл отчета в формате .xlsx\n\n"
        f"⚠️ Требования к файлу:\n"
        f"• Формат: .xlsx (Excel)\n"
        f"• Размер: до 50MB\n"
        f"• Содержание: детальная информация о пользователе\n\n"
        f"Отправьте XLSX файл в следующем сообщении.",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )
    
    # Register handler for file
    bot.register_next_step_handler(call.message, process_xlsx_report_file, report_id)




@bot.callback_query_handler(func=lambda call: call.data.startswith("reject_report_"))
def handle_reject_report(call):
    """Handle report rejection"""
    report_id = int(call.data.split("_")[2])
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Update report status to rejected
        cursor.execute('''
            UPDATE report_requests 
            SET status = 'rejected', admin_id = %s
            WHERE id = %s
        ''', (call.from_user.id, report_id))
        
        conn.commit()
        
        bot.answer_callback_query(
            call.id, 
            "❌ Запрос отклонен!", 
            show_alert=True)
        
        # Refresh report view
        try:
            handle_view_report(call)
        except Exception as e:
            logger.error(f"Error refreshing report view: {e}")
            # If there's an error, just show success message
            bot.answer_callback_query(
                call.id, 
                "❌ Запрос отклонен! Обновите страницу.", 
                show_alert=True
            )
        
    except Exception as e:
        logger.error(f"Error rejecting report: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("start_contract_"))
def handle_start_contract(call):
    """Handle starting work on contract"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Только администраторы могут управлять договорами", show_alert=True)
        return
    
    contract_id = int(call.data.split("_")[2])
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute('UPDATE contracts SET status = %s WHERE id = %s', ('processing', contract_id))
        conn.commit()
        
        bot.answer_callback_query(call.id, "✅ Договор взят в работу", show_alert=True)
        
        # Refresh the contract view
        call.data = f"admin_view_contract_{contract_id}"
        handle_admin_view_contract(call)
        
    except Exception as e:
        logger.error(f"Error starting contract {contract_id}: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при изменении статуса", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("attach_contract_"))
def handle_attach_contract(call):
    """Handle attaching contract file"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Только администраторы могут прикреплять договоры", show_alert=True)
        return
    
    contract_id = int(call.data.split("_")[2])
    
    # Store contract_id in user data for file handling
    bot.user_data[call.from_user.id] = {'attaching_contract': contract_id}
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data=f"admin_view_contract_{contract_id}"))
    
    bot.edit_message_text(
        f"📎 Прикрепление договора #{contract_id}\n\n"
        f"Отправьте файл договора в формате .txt\n\n"
        f"⚠️ Важно: файл должен быть в формате .txt",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )
    
    # Register handler for file
    bot.register_next_step_handler(call.message, process_contract_file, contract_id)




@bot.callback_query_handler(func=lambda call: call.data.startswith("complete_contract_"))
def handle_complete_contract(call):
    """Handle completing contract"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Только администраторы могут завершать договоры", show_alert=True)
        return
    
    contract_id = int(call.data.split("_")[2])
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Check if contract file is attached
        cursor.execute('SELECT contract_file_id, user_id FROM contracts WHERE id = %s', (contract_id,))
        result = cursor.fetchone()
        
        if not result:
            bot.answer_callback_query(call.id, "❌ Договор не найден", show_alert=True)
            return
        
        contract_file_id, user_id = result
        
        if not contract_file_id:
            bot.answer_callback_query(call.id, "❌ Сначала прикрепите файл договора", show_alert=True)
            return
        
        # Update status and completion date
        cursor.execute(
            'UPDATE contracts SET status = %s, completed_at = %s WHERE id = %s',
            ('completed', datetime.now(), contract_id)
        )
        conn.commit()
        
        # Notify user
        try:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📋 Мои договоры", callback_data="my_contracts"))
            
            bot.send_message(
                user_id,
                f"✅ Ваш договор готов!\n\n"
                f"📋 Договор #{contract_id} был завершен администратором.\n"
                f"📎 Файл договора прикреплен\n\n"
                f"Просмотрите договор в разделе '📋 Получить договор'",
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Failed to notify user {user_id}: {e}")
        
        bot.answer_callback_query(call.id, "✅ Договор завершен", show_alert=True)
        
        # Refresh the contract view
        call.data = f"admin_view_contract_{contract_id}"
        handle_admin_view_contract(call)
        
    except Exception as e:
        logger.error(f"Error completing contract {contract_id}: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при завершении договора", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("copy_referral_"))
def handle_copy_referral(call):
    """Handle referral link copy request"""
    referral_code = call.data.split("_")[2]
    bot_username = bot.get_me().username
    referral_link = f"https://t.me/{bot_username}?start={referral_code}"
    
    bot.answer_callback_query(
        call.id, 
        f"🔗 Реферальная ссылка скопирована!\n\n{referral_link}", 
        show_alert=True
    )




