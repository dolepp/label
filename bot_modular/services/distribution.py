# -*- coding: utf-8 -*-
"""Сервис дистрибуции: форма релиза, шаги, предпросмотр."""
import logging
from telebot import types

logger = logging.getLogger(__name__)


class ImprovedDistributionForm:
    """Улучшенная форма дистрибуции с полной навигацией (18 шагов Single)."""
    def __init__(self, release_type="single"):
        self.release_type = release_type
        self.data = {}
        self.current_step = 0
        self.message_id = None
        self.chat_id = None
        self.user_id = None

        self.steps = [
            ("artist_name", 
             "🎤 3) Исполнитель(-и):\n\n"
             "⌨️ Укажите основного исполнителя или группу:\n\n"
             "💡 Примеры:\n"
             "• Артист Исполнитель\n"
             "• The Music Band\n"
             "• Singer feat. Rapper\n\n"
             "📝 Если несколько исполнителей, перечислите через запятую:", "text"),
            
            ("release_name", 
             "💿 4) Название релиза:\n\n"
             "🎵 Введите название вашего сингла:\n\n"
             "💡 Примеры:\n"
             "• Моя Лучшая Песня\n"
             "• Summer Hit 2024\n"
             "• Love Ballad (Radio Edit)\n\n"
             "📝 Название должно соответствовать аудиофайлу:", "text"),
            
            ("producer", 
             "🎹 5) prod. by (будет указан в формате [prod.by yourbeatmaker]):\n\n"
             "⌨️ Укажите продюсера/битмейкера:\n\n"
             "💡 Примеры:\n"
             "• BeatMaker\n"
             "• ProducerName\n"
             "• YourBeatMaker\n\n"
             "📝 Будет отображаться как: [prod.by Ваш Продюсер]", "text"),
            
            ("genre", 
             "🎶 6) Жанр релиза:\n\n"
             "🎶 Укажите музыкальный жанр вашего релиза:\n\n"
             "💡 Популярные жанры:\n"
             "• Hip-Hop, Rap, Trap\n"
             "• Pop, Dance, House\n"
             "• Rock, Alternative, Indie\n"
             "• R&B, Soul, Jazz\n"
             "• Electronic, Techno, Dubstep\n\n"
             "📝 Введите один основной жанр:", "text"),
            
            ("cover", 
             "🖼 7) Обложка релиза (PNG, JPG 3000x3000):\n\n"
             "📸 Как фото (быстро, сжатое)\n"
             "📎 Как документ (лучшее качество, несжатое)\n\n"
             "💡 Для лучшего качества ОБЯЗАТЕЛЬНО отправляйте как документ:\n"
             "• Нажмите на скрепку 📎\n"
             "• Выберите 'Файл' или 'Документ'\n"
             "• Выберите файл обложки\n\n"
             "⚠️ ВАЖНО: Отправка как фото значительно снижает качество!\n\n"
             "✅ Поддерживаемые форматы: PNG, JPG, JPEG, WEBP\n"
             "📏 Рекомендуемый размер: 3000х3000 пикселей\n"
             "📦 Максимальный размер файла: 100 МБ", "photo"),
            
            ("audio", 
             "🎵 8) Файл трека (WAV, STEREO):\n\n"
             "🎧 Загрузите аудиофайл вашего трека:\n\n"
             "💡 Рекомендуемые форматы:\n"
             "• WAV (несжатый, лучшее качество)\n"
             "• MP3 (сжатый, меньший размер)\n"
             "• FLAC (сжатый без потерь)\n\n"
             "📊 Технические требования:\n"
             "• Формат: STEREO (стерео)\n"
             "• Качество: не менее 44.1 kHz / 16 bit\n"
             "• Максимальный размер: 100 MB\n\n"
             "📎 Отправьте файл как документ для сохранения качества:", "audio"),
            
            ("release_date", 
             "📅 9) Дата релиза (в формате ДД.ММ.ГГГГ):\n\n"
             "📅 Формат: ДД.ММ.ГГГГ (например: 25.12.2024)\n\n"
             "⚠️ Важные моменты:\n"
             "• Дата должна быть в будущем\n"
             "• Для промо поддержки подавайте заявку за 2 недели до релиза\n"
             "• Учитывайте время обработки заявки (3-7 дней)\n\n"
             "✍️ Введите дату релиза:", "text"),
            
            ("performer_name", 
             "👤 10) ФИО Исполнителя (-ей):\n\n"
             "✍️ Укажите полное имя исполнителя для официальных документов:\n\n"
             "💡 Примеры:\n"
             "• Иванов Иван Иванович\n"
             "• Петрова Анна Сергеевна\n"
             "• Smith John Michael\n\n"
             "📝 Важно:\n"
             "• Указывайте реальное ФИО (как в паспорте)\n"
             "• Если несколько исполнителей, перечислите через запятую\n"
             "• Эта информация нужна для договоров с площадками:", "text"),
            
            ("music_author", 
             "✍️ 11) ФИО Автора (-ов) музыки:\n\n"
             "🎵 Укажите автора(ов) музыкальной композиции:\n\n"
             "💡 Примеры:\n"
             "• Композиторов Алексей Владимирович\n"
             "• Musicmaker Ivan Petrov\n"
             "• Иванов И.И., Петров П.П.\n\n"
             "📜 Важные моменты:\n"
             "• Автор музыки - тот, кто создал мелодию\n"
             "• Может отличаться от исполнителя\n"
             "• Если несколько авторов, перечислите через запятую\n"
             "• Указывайте полные ФИО для авторских прав:", "text"),
            
            ("beat_contract", 
             "📄 12) ДОГОВОР НА БИТ\n\n"
             "📎 Загрузите договор на использование бита:\n\n"
             "💡 Что это:\n"
             "• Документ, подтверждающий права на использование инструментала\n"
             "• Договор с битмейкером/продюсером\n"
             "• Лицензия на бит\n\n"
             "📎 Форматы файлов:\n"
             "• PDF, DOC, DOCX, JPG, PNG\n"
             "• Максимальный размер: 10 MB\n\n"
             "⚠️ Важно: без этого документа релиз не может быть опубликован на площадках:", "document"),
            
            ("videoshot_url", 
             "🎥 13) Ссылка на видеошот для Яндекс.Музыки (если нет, напишите 'нет'):\n\n"
             "🎥 Видеошот - короткий вертикальный клип для промо:\n\n"
             "💡 Что это:\n"
             "• Короткое видео (15-30 сек) в вертикальном формате\n"
             "• Используется для продвижения в Яндекс.Музыке\n"
             "• Может содержать отрывок трека + визуал\n\n"
             "📎 Как отправить:\n"
             "• Загрузите видео на YouTube, VK, или другую платформу\n"
             "• Отправьте ссылку на видео\n"
             "• Если видеошота нет, напишите 'нет'\n\n"
             "✍️ Введите ссылку или 'нет':", "text"),
            
            ("explicit_content", 
             "🔞 14) Нецензурная лексика в треке (маты):", "yes_no"),
            
            ("lyrics_file", 
             "📝 15) Текст трека файлом в формате txt:", "document"),
            
            ("preview_start", 
             "⏱ 16) Начало предпрослушивания (секунда начала звука, например 90 для 1:30):", "text"),
            
            ("yandex_soon", 
             "🎤 17) Плашка 'скоро новый релиз' на Яндекс.Музыке:", "yes_no"),
            
            ("platform_links", 
             "🔗 18) Сделать ссылку на все площадки?", "yes_no"),
            
            ("tiktok_commercial", 
             "🎵 19) Разрешить коммерческое использование в TikTok?", "yes_no"),
            
            ("tiktok_full", 
             "🎶 20) Разрешить полную версию трека в TikTok?", "yes_no"),
        ]

    def get_current_step(self):
        if self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def get_progress(self):
        return f"📊 Шаг {self.current_step + 1} из {len(self.steps)}"

    def has_answer(self, step_index=None):
        if step_index is None:
            step_index = self.current_step
        if step_index >= len(self.steps):
            return False
        field_name = self.steps[step_index][0]
        return field_name in self.data and self.data[field_name]


def build_distribution_step_text(form):
    """Собрать текст и тип поля для текущего шага формы."""
    step = form.get_current_step()
    if not step:
        return None, None, None
    field_name, question, field_type = step
    current_value = form.data.get(field_name, "")
    text = question + "\n\n" + form.get_progress()
    if current_value:
        if field_type in ["photo", "audio", "document"]:
            text += "\n\n✅ Файл загружен"
        else:
            value_display = current_value if len(str(current_value)) < 100 else str(current_value)[:100] + "..."
            text += f"\n\n✅ Ваш ответ: {value_display}"
    return text, field_type, current_value


def build_distribution_preview_text(form):
    """Текст предпросмотра релиза."""
    text = "📝 ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР РЕЛИЗА\n\n"
    text += f"🎤 Исполнитель: {form.data.get('artist_name', '-')}\n"
    text += f"💿 Название: {form.data.get('release_name', '-')}\n"
    text += f"🎹 Продюсер: {form.data.get('producer', '-')}\n"
    text += f"🎶 Жанр: {form.data.get('genre', '-')}\n"
    text += f"📅 Дата: {form.data.get('release_date', '-')}\n"
    text += f"🔞 Маты: {form.data.get('explicit_content', '-')}\n\n"
    return text
