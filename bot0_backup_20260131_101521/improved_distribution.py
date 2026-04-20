"""
Улучшенная версия процесса дистрибуции с редактированием сообщений
и навигацией вперед/назад
"""

# Структура шагов дистрибуции
DISTRIBUTION_STEPS = [
    {
        'key': 'release_type',
        'question': '2) Тип релиза:\n\n'
                   '🎵 Выберите тип вашего релиза:\n\n'
                   '• Сингл - одна композиция\n'
                   '• EP - мини-альбом (2-6 треков)\n'
                   '• Альбом - полноценный альбом (7+ треков)',
        'type': 'buttons',
        'buttons': ['Сингл', 'EP', 'Альбом']
    },
    {
        'key': 'artist_name',
        'question': '3) Исполнитель(-и):\n\n'
                   '🎤 Укажите основного исполнителя или группу:\n\n'
                   '💡 Примеры:\n'
                   '• "Артист Исполнитель"\n'
                   '• "The Music Band"\n'
                   '• "Singer feat. Rapper"\n\n'
                   '📝 Если несколько исполнителей, перечислите через запятую:',
        'type': 'text'
    },
    {
        'key': 'release_name',
        'question': '4) Название релиза:\n\n'
                   '🎵 Введите название вашего сингла:\n\n'
                   '💡 Примеры:\n'
                   '• "Моя Лучшая Песня"\n'
                   '• "Summer Hit 2024"\n'
                   '• "Love Ballad (Radio Edit)"\n\n'
                   '📝 Название должно соответствовать аудиофайлу:',
        'type': 'text'
    },
    {
        'key': 'producer',
        'question': '5) prod. by (будет указан в формате [prod.by yourbeatmaker]):\n\n'
                   '🎛️ Укажите продюсера/битмейкера:\n\n'
                   '💡 Примеры:\n'
                   '• "BeatMaker"\n'
                   '• "ProducerName"\n'
                   '• "YourBeatMaker"\n\n'
                   '📝 Будет отображаться как: [prod.by ВашПродюсер]',
        'type': 'text'
    },
    {
        'key': 'genre',
        'question': '6) Жанр релиза:\n\n'
                   '🎼 Укажите музыкальный жанр вашего релиза:\n\n'
                   '💡 Популярные жанры:\n'
                   '• Hip-Hop, Rap, Trap\n'
                   '• Pop, Dance, House\n'
                   '• Rock, Alternative, Indie\n'
                   '• R&B, Soul, Jazz\n'
                   '• Electronic, Techno, Dubstep\n\n'
                   '📝 Введите один основной жанр:',
        'type': 'text'
    },
    {
        'key': 'cover',
        'question': '7) Обложка релиза (PNG, JPG 3000x3000):\n\n'
                   '🎨 Отправьте обложку:\n'
                   '📎 ОБЯЗАТЕЛЬНО как документ для лучшего качества\n\n'
                   '💡 Как отправить:\n'
                   '• Нажмите на скрепку 📎\n'
                   '• Выберите "Файл" или "Документ"\n'
                   '• Выберите файл обложки\n\n'
                   '⚠️ ВАЖНО: Отправка как фото снижает качество!\n'
                   '✅ Форматы: PNG, JPG, JPEG, WEBP\n'
                   '📐 Размер: 3000x3000 пикселей\n'
                   '💾 Макс. размер: 100 MB',
        'type': 'file'
    },
    {
        'key': 'audio',
        'question': '8) Аудиофайл релиза:\n\n'
                   '🎧 Отправьте аудиофайл вашего релиза:\n\n'
                   '⚠️ ВАЖНО: Отправьте ФАЙЛОМ (как документ), НЕ аудио!\n\n'
                   '💡 Как отправить правильно:\n'
                   '• Нажмите на скрепку 📎\n'
                   '• Выберите "Файл" или "Документ"\n'
                   '• Выберите ваш аудиофайл\n\n'
                   '✅ Поддерживаемые форматы: WAV, FLAC, MP3\n'
                   '📊 Рекомендуемое качество: WAV 16-bit/44.1kHz или выше\n'
                   '💾 Максимальный размер файла: 100 MB',
        'type': 'file'
    }
]


def create_navigation_markup(step_index, has_answer=False):
    """Создает клавиатуру с кнопками навигации"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    buttons = []
    
    # Кнопка "Назад" (всегда доступна, кроме первого шага)
    if step_index > 0:
        buttons.append(types.InlineKeyboardButton("◀️ Назад", callback_data=f"dist_prev_{step_index}"))
    
    # Кнопка "Вперед" (доступна только если есть ответ)
    if has_answer and step_index < len(DISTRIBUTION_STEPS) - 1:
        buttons.append(types.InlineKeyboardButton("Вперед ▶️", callback_data=f"dist_next_{step_index}"))
    
    if buttons:
        markup.row(*buttons)
    
    # Кнопка "Изменить" (если есть ответ)
    if has_answer:
        markup.add(types.InlineKeyboardButton("✏️ Изменить", callback_data=f"dist_edit_{step_index}"))
    
    # Кнопка "Отмена"
    markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="dist_cancel"))
    
    return markup


def get_step_text(step_index, user_data):
    """Получить текст для текущего шага с информацией о заполненных данных"""
    step = DISTRIBUTION_STEPS[step_index]
    text = step['question']
    
    # Добавляем информацию о текущем ответе, если есть
    if step['key'] in user_data:
        value = user_data[step['key']]
        if step['type'] == 'file':
            text += f"\n\n✅ Текущий файл: загружен"
        else:
            text += f"\n\n✅ Текущий ответ: {value}"
    
    # Добавляем прогресс
    progress = f"\n\n📊 Прогресс: {step_index + 1}/{len(DISTRIBUTION_STEPS)}"
    text += progress
    
    return text


def show_distribution_step(message_or_call, step_index, user_id, edit=False):
    """Показать шаг дистрибуции"""
    # Получаем или создаем данные пользователя
    if user_id not in bot.user_data:
        bot.user_data[user_id] = {}
    
    user_data = bot.user_data[user_id]
    user_data['current_step'] = step_index
    
    step = DISTRIBUTION_STEPS[step_index]
    has_answer = step['key'] in user_data
    
    text = get_step_text(step_index, user_data)
    markup = create_navigation_markup(step_index, has_answer)
    
    # Если это callback (редактирование), редактируем сообщение
    if edit and isinstance(message_or_call, types.CallbackQuery):
        try:
            bot.edit_message_text(
                text,
                message_or_call.message.chat.id,
                message_or_call.message.message_id,
                reply_markup=markup
            )
            bot.answer_callback_query(message_or_call.id)
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            # Если не удалось отредактировать, отправляем новое
            bot.send_message(message_or_call.message.chat.id, text, reply_markup=markup)
    else:
        # Отправляем новое сообщение
        chat_id = message_or_call.chat.id if hasattr(message_or_call, 'chat') else message_or_call.message.chat.id
        sent_msg = bot.send_message(chat_id, text, reply_markup=markup)
        # Сохраняем ID сообщения для последующего редактирования
        user_data['message_id'] = sent_msg.message_id
    
    # Регистрируем обработчик для текстового ответа
    if step['type'] == 'text':
        bot.register_next_step_handler_by_chat_id(
            chat_id if hasattr(message_or_call, 'chat') else message_or_call.message.chat.id,
            lambda msg: handle_distribution_text_answer(msg, step_index)
        )


# Обработчики callback для навигации
@bot.callback_query_handler(func=lambda call: call.data.startswith("dist_prev_"))
def handle_dist_prev(call):
    """Перейти к предыдущему шагу"""
    step_index = int(call.data.split("_")[-1])
    if step_index > 0:
        show_distribution_step(call, step_index - 1, call.from_user.id, edit=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith("dist_next_"))
def handle_dist_next(call):
    """Перейти к следующему шагу"""
    step_index = int(call.data.split("_")[-1])
    user_data = bot.user_data.get(call.from_user.id, {})
    
    # Проверяем, что текущий шаг заполнен
    current_step = DISTRIBUTION_STEPS[step_index]
    if current_step['key'] not in user_data:
        bot.answer_callback_query(call.id, "⚠️ Сначала заполните текущий шаг!", show_alert=True)
        return
    
    if step_index < len(DISTRIBUTION_STEPS) - 1:
        show_distribution_step(call, step_index + 1, call.from_user.id, edit=True)
    else:
        # Последний шаг - показываем итоги
        show_distribution_summary(call)


@bot.callback_query_handler(func=lambda call: call.data.startswith("dist_edit_"))
def handle_dist_edit(call):
    """Изменить ответ на текущем шаге"""
    step_index = int(call.data.split("_")[-1])
    user_id = call.from_user.id
    
    # Удаляем текущий ответ
    step = DISTRIBUTION_STEPS[step_index]
    if user_id in bot.user_data and step['key'] in bot.user_data[user_id]:
        del bot.user_data[user_id][step['key']]
    
    # Показываем шаг заново
    show_distribution_step(call, step_index, user_id, edit=True)


@bot.callback_query_handler(func=lambda call: call.data == "dist_cancel")
def handle_dist_cancel(call):
    """Отмена процесса дистрибуции"""
    user_id = call.from_user.id
    if user_id in bot.user_data:
        bot.user_data[user_id].clear()
    
    bot.edit_message_text(
        "❌ Процесс создания релиза отменен.",
        call.message.chat.id,
        call.message.message_id
    )
    bot.answer_callback_query(call.id, "Отменено")


def handle_distribution_text_answer(message, step_index):
    """Обработка текстового ответа"""
    user_id = message.from_user.id
    
    if user_id not in bot.user_data:
        bot.send_message(message.chat.id, "❌ Сессия устарела. Начните заново.")
        return
    
    step = DISTRIBUTION_STEPS[step_index]
    bot.user_data[user_id][step['key']] = message.text
    
    # Редактируем предыдущее сообщение с вопросом
    if 'message_id' in bot.user_data[user_id]:
        try:
            text = get_step_text(step_index, bot.user_data[user_id])
            markup = create_navigation_markup(step_index, has_answer=True)
            bot.edit_message_text(
                text,
                message.chat.id,
                bot.user_data[user_id]['message_id'],
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
    
    # Удаляем сообщение пользователя с ответом
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except:
        pass


def show_distribution_summary(call):
    """Показать итоговую информацию перед отправкой"""
    user_data = bot.user_data.get(call.from_user.id, {})
    
    text = "📋 **Проверьте введенные данные:**\n\n"
    
    for i, step in enumerate(DISTRIBUTION_STEPS):
        if step['key'] in user_data:
            value = user_data[step['key']]
            if step['type'] == 'file':
                text += f"{i+2}. {step['key']}: ✅ Загружен\n"
            else:
                text += f"{i+2}. {step['key']}: {value}\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Подтвердить", callback_data="dist_submit"),
        types.InlineKeyboardButton("◀️ Назад", callback_data=f"dist_prev_{len(DISTRIBUTION_STEPS)-1}")
    )
    markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="dist_cancel"))
    
    bot.edit_message_text(
        text,
        call.message.chat.id,
        call.message.message_id,
        parse_mode='Markdown',
        reply_markup=markup
    )


# Функция для запуска процесса дистрибуции
def start_distribution(message):
    """Начать процесс дистрибуции"""
    user_id = message.from_user.id
    bot.user_data[user_id] = {}
    show_distribution_step(message, 0, user_id, edit=False)

