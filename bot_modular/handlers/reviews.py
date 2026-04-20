"""Handlers: register on bot."""
from core.bot import bot
from handlers.common import *  # noqa: F401,F403

@bot.callback_query_handler(func=lambda call: call.data.startswith("review_create_"))
def start_review_creation(call):
    """Start review creation process"""
    category = call.data.split("_")[2]
    bot.review_category = category  # Сохраняем категорию

    markup = create_rating_keyboard()
    bot.edit_message_text(
        f"⭐️ Оцените услугу '{category}' от 1 до 5 звезд:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )




@bot.callback_query_handler(func=lambda call: call.data == "reviews_view_menu")
def handle_reviews_view_menu(call):
    """Show categories for viewing reviews"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🎵 Дистрибуция", callback_data="reviews_category_distribution"),
        types.InlineKeyboardButton("🎨 Обложки + Motion", callback_data="reviews_category_design"),
        types.InlineKeyboardButton("🔄 Случайный отзыв", callback_data="reviews_random"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="reviews_back_main")
    )

    bot.edit_message_text(
        "📂 Выберите категорию отзывов:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )




@bot.callback_query_handler(func=lambda call: call.data == "reviews_random")
def handle_reviews_random(call):
    """Handle random review request"""
    show_random_review(call.message)




@bot.callback_query_handler(func=lambda call: call.data == "reviews_back_main")
def handle_reviews_back_main(call):
    """Return to main reviews menu (actions)"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👀 Посмотреть отзывы", callback_data="reviews_view_menu"),
        types.InlineKeyboardButton("✍️ Оставить отзыв", callback_data="reviews_create_menu")
    )

    bot.edit_message_text(
        "⭐️ Отзывы\n\nВыберите действие:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )




@bot.callback_query_handler(func=lambda call: call.data.startswith(("approve_review_", "reject_review_")))
def handle_review_moderation(call):
    """Handle review approval/rejection"""
    action = "approve" if call.data.startswith("approve") else "reject"
    review_id = int(call.data.split("_")[2])

    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Database error", show_alert=True)
        return

    try:
        cursor = conn.cursor()

        if action == "approve":
            # Обновляем статус отзыва
            cursor.execute('''
                UPDATE reviews SET status = 'approved' WHERE id = %s
            ''', (review_id,))
            message = "✅ Отзыв одобрен и опубликован"
        else:
            # Удаляем отзыв
            cursor.execute('''
                DELETE FROM reviews WHERE id = %s
            ''', (review_id,))
            message = "❌ Отзыв отклонен и удален"

        conn.commit()

        # Обновляем сообщение у администратора
        try:
            bot.edit_message_text(
                f"{call.message.text}\n\n{message}",
                call.message.chat.id,
                call.message.message_id
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")

        bot.answer_callback_query(call.id, message)

    except Exception as e:
        logger.error(f"Error moderating review: {e}")
        bot.answer_callback_query(call.id, "❌ Error processing request", show_alert=True)
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.callback_query_handler(func=lambda call: call.data.startswith("review_create"))
def start_review_creation(call):
    """Start review creation process"""
    if "_" in call.data:
        category = call.data.split("_")[2]
        bot.review_category = category
    else:
        markup = types.InlineKeyboardMarkup()
        categories = [
            ("🎵 Дистрибуция", "distribution"),
            ("🎨 Обложки + Motion", "design"),
            (" IZBA Records", "izba")
        ]

        for text, category in categories:
            markup.add(types.InlineKeyboardButton(text, callback_data=f"review_category_{category}"))

        bot.edit_message_text(
            "Выберите категорию для отзыва:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        return

    bot.edit_message_text(
        "Оцените сервис от 1 до 5 звезд:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=create_rating_keyboard()
    )




@bot.callback_query_handler(func=lambda call: call.data.startswith("rating_"))
def handle_rating(call):
    """Handle rating selection"""
    rating = int(call.data.split("_")[1])
    bot.review_rating = rating  # Сохраняем рейтинг

    bot.edit_message_text(
        f"⭐️ Вы поставили {rating} {'звезд' if rating > 1 else 'звезду'}!\n\n"
        "📝 Теперь напишите текст вашего отзыва:",
        call.message.chat.id,
        call.message.message_id
    )
    bot.register_next_step_handler(call.message, save_review)




@bot.callback_query_handler(
    func=lambda call: call.data.startswith("review_approve_") or call.data.startswith("review_reject_"))
def handle_review_moderation(call):
    """Handle review approval/rejection"""
    action, review_id = call.data.split("_")[1:]
    review_id = int(review_id)

    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(
            call.id,
            "❌ Ошибка подключения к базе данных. Попробуйте позже.",
            show_alert=True
        )
        return

    try:
        cursor = conn.cursor()

        if action == "approve":
            cursor.execute('UPDATE reviews SET status = %s WHERE id = %s', ("approved", review_id))
            status_text = "✅ Отзыв одобрен"
        else:
            cursor.execute('DELETE FROM reviews WHERE id = %s', (review_id,))
            status_text = "❌ Отзыв отклонен"

        conn.commit()

        # Edit the original message to show the result
        try:
            bot.edit_message_text(
                f"{call.message.text}\n\n{status_text}",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=None  # remove buttons
            )
        except Exception as e:
            logger.error(f"Could not edit message: {e}")

        bot.answer_callback_query(call.id, status_text)

    except Error as e:
        logger.error(f"PostgreSQL error in handle_review_moderation: {e}")
        bot.answer_callback_query(
            call.id,
            "❌ Произошла ошибка при модерации отзыва.",
            show_alert=True
        )
    finally:
        if conn:
            cursor.close()
            return_pg_connection(conn)




@bot.message_handler(func=lambda message: message.text == "⭐️ Отзывы")
def handle_reviews_menu(message):
    """Handle reviews menu"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👀 Посмотреть отзывы", callback_data="reviews_view_menu"),
        types.InlineKeyboardButton("✍️ Оставить отзыв", callback_data="reviews_create_menu")
    )

    bot.reply_to(
        message,
        "⭐️ Отзывы\n\nВыберите действие:",
        reply_markup=markup
    )




