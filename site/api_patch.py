#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Патч для обновления api.py

import sys

# Читаем файл
with open('/home/goida/label/site/api.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Заменяем сообщение админам на полное
old_msg = '''            notification_message = f"""
🎵 <b>Новый релиз для дистрибуции!</b>

👤 <b>Исполнитель:</b> {user_name} (@{user_username})
🎼 <b>Название:</b> {release_data['releaseName']}
🎭 <b>Артист:</b> {release_data['artistName']}
📀 <b>Тип:</b> {release_data['releaseType']}
🎵 <b>Жанр:</b> {release_data['genre']}
📅 <b>Дата релиза:</b> {release_data['releaseDate']}

🆔 <b>ID релиза:</b> {release_id}
💰 <b>Стоимость:</b> {'Бесплатно' if is_artist else 'Платно'}
            """'''

new_msg = '''            # Формируем полное сообщение в формате бота
            producer = request.form.get('producer', '')
            is_album = release_data['releaseType'] in ['ALBUM', 'EP', 'Maxi Single']
            
            notification_message = "📢 <b>Новый релиз на проверку!</b>\n\n"
            notification_message += f"🎤 <b>Артист:</b> {user_name} (@{user_username})\n"
            notification_message += f"🎵 <b>Название:</b> {release_data['releaseName']}\n"
            
            if producer:
                notification_message += f"🎹 <b>Продюсер:</b> {producer}\n"
            
            notification_message += f"🎭 <b>Артист (исполнитель):</b> {release_data['artistName']}\n"
            notification_message += f"👤 <b>Исполнитель:</b> {release_data['performerName']}\n"
            notification_message += f"✍️ <b>Автор музыки:</b> {release_data['musicAuthor']}\n"
            notification_message += f"📀 <b>Тип:</b> {release_data['releaseType']}\n"
            notification_message += f"🎵 <b>Жанр:</b> {release_data['genre']}\n"
            notification_message += f"📅 <b>Дата релиза:</b> {release_data['releaseDate']}\n"
            
            notification_message += "\n<b>Дополнительные опции:</b>\n"
            notification_message += f"🔞 <b>Explicit контент:</b> {'Да' if release_data.get('explicitContent') else 'Нет'}\n"
            if release_data.get('previewStart'):
                notification_message += f"⏱️ <b>Превью (сек):</b> {release_data['previewStart']}\n"
            notification_message += f"🟢 <b>Яндекс 'Скоро':</b> {'Да' if release_data.get('yandexSoon') else 'Нет'}\n"
            notification_message += f"🔗 <b>Создать ссылки:</b> {'Да' if release_data.get('createLinks') else 'Нет'}\n"
            notification_message += f"📱 <b>TikTok коммерч.:</b> {'Да' if release_data.get('tiktokCommercial') else 'Нет'}\n"
            notification_message += f"🎵 <b>TikTok полная версия:</b> {'Да' if release_data.get('tiktokFullVersion') else 'Нет'}\n"
            
            # Для синглов добавляем информацию о тексте трека
            if not is_album and lyrics_file_id:
                notification_message += f"\n📜 <b>Текст трека:</b> Прикреплен (file_id: {lyrics_file_id[:20]}...)\n"
            
            notification_message += f"\n🆔 <b>ID релиза:</b> {release_id}\n"
            notification_message += f"💰 <b>Стоимость:</b> {'Бесплатно' if is_artist else 'Платно'}\n"'''

if old_msg in content:
    content = content.replace(old_msg, new_msg)
    with open('/home/goida/label/site/api.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Файл обновлен успешно!")
    sys.exit(0)
else:
    print("Не удалось найти старый текст сообщения")
    sys.exit(1)

