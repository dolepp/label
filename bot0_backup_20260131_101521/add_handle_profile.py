#!/usr/bin/env python3
"""
Добавление функции handle_profile в label.py
"""

# Читаем файл
with open('label.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Находим строку с комментарием "# Profile callback handlers"
insert_pos = None
for i, line in enumerate(lines):
    if '# Profile callback handlers' in line:
        insert_pos = i
        break

if insert_pos is None:
    print("❌ Не найден комментарий '# Profile callback handlers'")
    exit(1)

# Создаем новую функцию
new_function = '''
def handle_profile(message):
    """Handle profile menu"""
    user_id = message.from_user.id
    
    try:
        conn = get_pg_connection()
        if not conn:
            bot.send_message(message.chat.id, "❌ Ошибка подключения к базе данных")
            return
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, email, COALESCE(balance, 0)
            FROM label
            WHERE telegram_id = %s
        """, (user_id,))
        
        user_data = cursor.fetchone()
        cursor.close()
        
        if not user_data:
            bot.send_message(message.chat.id, "❌ Профиль не найден")
            return_pg_connection(conn)
            return
        
        name, email, balance = user_data
        
        # Создаем клавиатуру профиля
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("📝 Мои данные", callback_data="profile_data"),
            types.InlineKeyboardButton("💰 Финансы", callback_data="profile_finance"),
            types.InlineKeyboardButton("🎵 Релизы", callback_data="profile_releases"),
            types.InlineKeyboardButton("📅 Букинг", callback_data="profile_bookings"),
            types.InlineKeyboardButton("🎨 Заказы дизайна", callback_data="profile_orders"),
            types.InlineKeyboardButton("👥 Реферальная программа", callback_data="profile_referral")
        )
        markup.add(types.InlineKeyboardButton("◀️ Главное меню", callback_data="back_main"))
        
        profile_text = f"""
👤 **Ваш профиль**

👨‍💼 Имя: {name or 'Не указано'}
📧 Email: {email or 'Не указан'}
💰 Баланс: {balance} ₽

Выберите раздел:
"""
        
        bot.send_message(
            message.chat.id,
            profile_text,
            parse_mode='Markdown',
            reply_markup=markup
        )
        
    except Exception as e:
        logger.error(f"Error handling profile: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка при загрузке профиля")
    finally:
        return_pg_connection(conn)

'''

# Вставляем функцию перед комментарием
lines.insert(insert_pos, new_function)

# Сохраняем файл
with open('label_with_profile.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("✅ Функция handle_profile добавлена")
print("✅ Файл сохранен как label_with_profile.py")
print("\nПрименить изменения:")
print("cp label_with_profile.py label.py")

