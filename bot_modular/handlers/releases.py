"""Handlers: register on bot."""
from core.bot import bot
from handlers.common import *  # noqa: F401,F403

@bot.callback_query_handler(func=lambda call: call.data == "releases_approve" or call.data == "releases_reject")
def handle_release_status_change(call):
    """Handle release approval/rejection request"""
    action = "approve" if call.data == "releases_approve" else "reject"
    bot.edit_message_text(
        "Введите ID релиза для изменения статуса:",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(call.message, process_release_id, action)




@bot.callback_query_handler(func=lambda call: call.data == "releases_approve" or call.data == "releases_reject")
def handle_release_status_change(call):
    """Handle release approval/rejection request"""
    action = "approve" if call.data == "releases_approve" else "reject"
    bot.edit_message_text(
        "Введите ID релиза для изменения статуса:",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(call.message, process_release_id, action)




@bot.callback_query_handler(func=lambda call: call.data.startswith("status_update_"))
def handle_status_update(call):
    """Handle status update selection"""
    parts = call.data.split("_")
    release_id = int(parts[2])
    new_status = "_".join(parts[3:])  # Reconstruct status name

    # Update status in database
    if update_release_status(release_id, new_status):
        # Notify user
        notify_user_about_status_change(release_id, new_status)

        bot.answer_callback_query(
            call.id,
            f"✅ Статус обновлен на: {new_status}",
            show_alert=True
        )

        # Return to release details
        show_my_release_details(call, release_id, admin_mode=True)
    else:
        bot.answer_callback_query(
            call.id,
            "❌ Ошибка при обновлении статуса",
            show_alert=True
        )




@bot.callback_query_handler(func=lambda call: call.data == "confirm_report_request")
def handle_confirm_report_request(call):
    """Handle confirmation of report request"""
    user_id = call.from_user.id
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Create report request
        cursor.execute('''
            INSERT INTO report_requests (user_id, release_type, status, created_at, request_type)
            VALUES (%s, %s, %s, NOW(), %s)
            RETURNING id
        ''', (user_id, 'GENERAL', 'pending', 'Общий отчет по всем релизам'))
        
        report_id = cursor.fetchone()[0]
        
        # Get user info for admin notification
        cursor.execute('SELECT name, tg FROM label WHERE telegram_id = %s', (user_id,))
        user_info = cursor.fetchone()
        user_name = user_info[0] if user_info else "Неизвестный пользователь"
        username = user_info[1] if user_info else "нет username"
        
        conn.commit()
        
        # Confirm to user
        bot.edit_message_text(
            "✅ Запрос отчета успешно отправлен!\n\n"
            "📊 Ваш запрос на получение общего отчета по всем релизам принят в обработку.\n"
            "📊 Отчет будет сгенерирован в формате Excel (.xlsx)\n"
            "⏳ Обычно отчет готовится в течение 1-3 рабочих дней.\n\n"
            "Вы получите уведомление, когда отчет будет готов.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile")
            )
        )
        
        # Notify admins
        notify_admins_about_report_request(user_id, report_id, user_name, username)
        
        logger.info(f"User {user_id} requested report {report_id}")
        
    except Exception as e:
        logger.error(f"Error creating report request: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при создании запроса отчета", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data == "view_latest_report")
def handle_view_latest_report(call):
    """Handle viewing the latest report"""
    user_id = call.from_user.id
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Get latest report
        cursor.execute('''
            SELECT id, status, created_at, completed_at, report_file_id
            FROM report_requests 
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 1
        ''', (user_id,))
        
        report = cursor.fetchone()
        if not report:
            bot.answer_callback_query(call.id, "❌ Отчет не найден", show_alert=True)
            return
        
        report_id, status, created_at, completed_at, report_file_id = report
        
        # Format dates
        created_str = created_at.strftime('%d.%m.%Y %H:%M') if created_at else "дата не указана"
        completed_str = completed_at.strftime('%d.%m.%Y %H:%M') if completed_at else "не завершен"
        
        # Status emoji and text
        status_info = {
            'pending': ('⏳', 'В обработке'),
            'processing': ('🔄', 'Готовится'),
            'completed': ('✅', 'Готов'),
            'rejected': ('❌', 'Отклонен')
        }.get(status, ('❓', 'Неизвестно'))
        
        status_emoji, status_text = status_info
        
        # Create response text
        response_text = f"📊 Отчет #{report_id}\n\n"
        response_text += f"📅 Дата запроса: {created_str}\n"
        response_text += f"📊 Статус: {status_emoji} {status_text}\n"
        
        if status == 'completed' and completed_at:
            response_text += f"✅ Дата готовности: {completed_str}\n"
        
        if status == 'rejected':
            response_text += "\n❌ Отчет был отклонен. Обратитесь к администратору для уточнения деталей."
        
        # Create markup
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        if status == 'completed' and completed_at:
            markup.add(
                types.InlineKeyboardButton("📎 Скачать отчет (Excel)", callback_data=f"download_report_{report_id}"),
                types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_profile")
            )
        elif status == 'pending':
            markup.add(
                types.InlineKeyboardButton("❌ Отменить запрос", callback_data=f"cancel_report_{report_id}"),
                types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_profile")
            )
        else:
            markup.add(
                types.InlineKeyboardButton("◀️ Назад", callback_data="back_to_profile")
            )
    
        bot.edit_message_text(
            response_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error viewing latest report: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка при просмотре отчета", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith(("album_detail_", "my_release_detail_")) and not call.data.endswith("_admin"))
def handle_release_callback(call):
    """Handle release callbacks in user mode only"""
    try:
        if call.data.startswith("album_detail_"):
            parts = call.data.split('_')
            album_id = int(parts[2])
            show_album_details(call, album_id, admin_mode=False)
        elif call.data.startswith("my_release_detail_"):
            parts = call.data.split('_')
            release_id = int(parts[3])
            show_my_release_details(call, release_id, admin_mode=False)
    except Exception as e:
        logger.error(f"Error handling release callback: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)




@bot.callback_query_handler(func=lambda call: call.data.startswith("user_releases_"))
def handle_user_releases(call):
    """Show user's releases in admin mode"""
    user_id = int(call.data.split('_')[2])
    handle_my_releases(call.message, user_id, admin_mode=True)




@bot.callback_query_handler(func=lambda call: call.data.startswith("album_status_update_"))
def handle_album_status_update(call):
    """Handle album status update request"""
    try:
        parts = call.data.split("_")
        album_id = int(parts[3])
        
        # Check admin access
        if not has_access_level(call.from_user.id, ["admin"]):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут изменять статус", show_alert=True)
            return
        
        # Create status selection keyboard
        markup = types.InlineKeyboardMarkup(row_width=1)
        
        # Add all status options
        for status in RELEASE_STATUSES:
            markup.add(types.InlineKeyboardButton(
                f"🔄 {status.capitalize()}",
                callback_data=f"album_status_confirm_{album_id}_{status}"
            ))
        
        # Add back button
        markup.add(types.InlineKeyboardButton(
            "◀️ Назад к альбому",
            callback_data=f"album_detail_{album_id}_admin"
        ))
        
        bot.edit_message_text(
            "🔄 Выберите новый статус для альбома:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error in handle_album_status_update: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)




@bot.callback_query_handler(func=lambda call: call.data.startswith("confirm_report_upload_"))
def handle_confirm_report_upload(call):
    """Handle report file upload confirmation"""
    report_id = int(call.data.split("_")[3])
    user_id = call.from_user.id
    
    # Check if user is admin
    if not has_access_level(user_id, ["admin"]):
        bot.answer_callback_query(call.id, "❌ Только администраторы могут прикреплять отчеты", show_alert=True)
        return
    
    # Get file info from user_data
    if not hasattr(bot, 'user_data') or user_id not in bot.user_data:
        bot.answer_callback_query(call.id, "❌ Информация о файле не найдена", show_alert=True)
        return
    
    file_info = bot.user_data[user_id].get('report_file_info')
    if not file_info or file_info['report_id'] != report_id:
        bot.answer_callback_query(call.id, "❌ Информация о файле не найдена", show_alert=True)
        return
    
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        
        # Update report request with file info
        cursor.execute('''
            UPDATE report_requests 
            SET report_file_id = %s, status = 'completed', completed_at = CURRENT_TIMESTAMP, admin_id = %s
            WHERE id = %s
        ''', (file_info['file_id'], user_id, report_id))
        
        conn.commit()
        
        # Get report details for notification
        cursor.execute('''
            SELECT rr.user_id, rr.release_type, rr.request_type, l.name, l.tg
            FROM report_requests rr
            JOIN label l ON rr.user_id = l.telegram_id
            WHERE rr.id = %s
        ''', (report_id,))
        
        report_info = cursor.fetchone()
        if report_info:
            report_user_id, release_type, request_type, user_name, username = report_info
            
            # Notify user that report is ready
            try:
                bot.send_message(
                    report_user_id,
                    f"✅ Ваш отчет готов!\n\n"
                    f"📊 Запрос: {request_type}\n"
                    f"🎵 Тип: {release_type}\n"
                    f"📎 Файл отчета прикреплен администратором"
                )
            except Exception as e:
                logger.error(f"Failed to notify user {report_user_id}: {e}")
        
        # Clean up user_data
        if user_id in bot.user_data:
            del bot.user_data[user_id]['report_file_info']
        
        bot.answer_callback_query(
            call.id, 
            "✅ Отчет успешно прикреплен!", 
            show_alert=True
        )
        
        # Return to report view
        try:
            handle_view_report(call)
        except Exception as e:
            logger.error(f"Error returning to report view: {e}")
            # If there's an error, just show success message
            bot.answer_callback_query(
                call.id, 
                "✅ Отчет успешно прикреплен! Обновите страницу.", 
                show_alert=True
            )
        
    except Exception as e:
        logger.error(f"Error updating report with file: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_release_"))
def handle_edit_release(call):
    """Handle edit release request"""
    release_id = call.data.split("_")[2]
    
    # Check if user owns this release
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return
    
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id, status FROM releases WHERE id = %s",
            (release_id,)
        )
        release = cursor.fetchone()
        
        if not release:
            bot.answer_callback_query(call.id, "❌ Релиз не найден", show_alert=True)
            return
        
        user_id, status = release
        
        # Check if user owns this release
        if user_id != call.from_user.id:
            bot.answer_callback_query(call.id, "❌ У вас нет прав для редактирования этого релиза", show_alert=True)
            return
        
        # Check if release can be edited
        if status not in ["В обработке", "Готов к отгрузке"]:
            bot.answer_callback_query(call.id, "❌ Этот релиз нельзя редактировать", show_alert=True)
            return
        
        # Start edit process
        bot.edit_message_text(
            "✏️ Выберите, что хотите изменить:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=create_edit_release_keyboard(release_id)
        )
        
    except Exception as e:
        logger.error(f"Error in handle_edit_release: {e}")
        bot.answer_callback_query(call.id, f"❌ Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)



@bot.callback_query_handler(func=lambda call: call.data.startswith("edit_release_name_"))
def handle_edit_release_name(call):
    """Handle edit release name request"""
    release_id = call.data.split("_")[3]
    
    bot.edit_message_text(
        "✏️ Введите новое название релиза:",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(call.message, process_edit_release_name, release_id)



