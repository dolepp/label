"""Support handlers for the modular bot."""
from __future__ import annotations

import logging
from typing import Any

from telebot import types

from core.config import CHANNEL_USERNAME, MANAGER_USERNAME, OWNER_USERNAME, PERMANENT_ADMINS, SUPPORT_HOURS
from db.repositories.support import (
    create_support_request,
    format_request_datetime,
    get_support_request,
    get_support_status_counts,
    is_admin_user,
    list_recent_support_requests,
    list_user_support_requests,
    update_support_status,
)
from keyboards.reply import create_main_menu


logger = logging.getLogger(__name__)

SUPPORT_REQUEST_STATUSES = ["принят", "требует уточнения", "решен"]

SUPPORT_TEMPLATES = [
    {
        "id": "moderation",
        "button": "⚡️ Ускорение модерации",
        "title": "Ускорение модерации",
        "description": "Если релиз завис на модерации, отправьте данные и мы уведомим площадки.",
        "fields": ["Исполнитель - название релиза"],
    },
    {
        "id": "videoshot",
        "button": "🎥 Видеошот",
        "title": "Заявка на видеошот",
        "description": "Для оформления видеошота нужны технические данные и ссылка на материалы.",
        "fields": [
            "Исполнитель - название трека",
            "UPC",
            "ISRC (если трек внутри альбома)",
            "Ссылка на диск с видеошотом",
        ],
        "note": "Требования: mp4/H.264, 720p, 15 секунд, желательно вертикальный формат без синхрона губ.",
    },
    {
        "id": "move_release",
        "button": "🔁 Переместить релиз",
        "title": "Перенос релиза в другую карточку",
        "description": "Поможем переместить релиз в нужную карточку артиста.",
        "fields": ["Ссылка на нужную карточку", "Ссылка на релиз", "UPC", "Никнейм"],
    },
    {
        "id": "remove_release",
        "button": "🧹 Убрать релизы",
        "title": "Удалить релизы из карточки",
        "description": "Укажите карточку и релизы, которые нужно убрать.",
        "fields": ["Ссылка на карточку", "Ссылки на релизы (каждый с новой строки)", "Никнейм"],
    },
    {
        "id": "youtube_verify",
        "button": "▶️ Верификация YouTube",
        "title": "Верификация YouTube-канала",
        "description": "Отправьте ссылки, если канал соответствует требованиям YouTube.",
        "fields": ["Ссылка на YouTube канал", "Ссылка на YouTube Topic", "Никнейм"],
        "note": "На канале должен быть тематический контент артиста и минимум один релиз от дистрибьютора.",
    },
    {
        "id": "set_photo",
        "button": "🖼 Установить фото",
        "title": "Поменять фотографию карточки",
        "description": "Загрузим новую фотографию артиста на нужной площадке.",
        "fields": ["Ссылка на карточку", "Ссылка на фотографию на диске", "Никнейм"],
    },
    {
        "id": "missing_store",
        "button": "🚫 Нет на витрине",
        "title": "Релиз отсутствует на площадке",
        "description": "Сообщите, где не отображается релиз.",
        "fields": ["Исполнитель - название релиза", "Нет на витрине ... (указать площадку)", "UPC", "Никнейм"],
    },
    {
        "id": "soundcloud_whitelist",
        "button": "☁️ Вайтлист SoundCloud",
        "title": "Добавление в вайтлист SoundCloud",
        "description": "Заявка на вайтлист для SoundCloud (YouTube не поддерживается).",
        "fields": ["Ссылка на профиль SoundCloud", "Никнейм"],
        "note": "Вайтлисты YouTube не оформляем.",
    },
]

MAIN_MENU_TEXTS = {
    "🎵 Наши услуги",
    "👤 Мой профиль",
    "⭐️ Отзывы",
    "❓ Помощь/вопросы",
    "🌐 Открыть приложение",
    "📊 Статистика",
    "📞 Поддержка",
    "ℹ️ О нас",
}


def _main_markup():
    return create_main_menu()


def _support_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=1)
    for template in SUPPORT_TEMPLATES:
        markup.add(types.InlineKeyboardButton(template["button"], callback_data=f"support_template:{template['id']}"))
    markup.add(types.InlineKeyboardButton("💬 Написать менеджеру", url=f"https://t.me/{MANAGER_USERNAME.lstrip('@')}"))
    return markup


def _cancel_keyboard():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="support_cancel"))
    return markup


def _status_keyboard(request_id: int, active_status: str | None = None):
    markup = types.InlineKeyboardMarkup(row_width=2)
    for status in SUPPORT_REQUEST_STATUSES:
        prefix = "✅ " if status == active_status else ""
        markup.add(types.InlineKeyboardButton(f"{prefix}{status.title()}", callback_data=f"support_status:{request_id}:{status}"))
    return markup


def _template_by_id(template_id: str) -> dict[str, Any] | None:
    return next((template for template in SUPPORT_TEMPLATES if template["id"] == template_id), None)


def _storage(bot, user_id: int) -> dict[str, Any]:
    if not hasattr(bot, "user_data"):
        bot.user_data = {}
    return bot.user_data.setdefault(user_id, {})


def _display_user(user) -> str:
    if getattr(user, "username", None):
        return f"@{user.username}"
    first_name = getattr(user, "first_name", None)
    return first_name or str(getattr(user, "id", "unknown"))


def _is_subscribed(bot, user_id: int) -> bool:
    try:
        member = bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as exc:
        logger.error("Could not check channel subscription for user %s: %s", user_id, exc)
        return False


def _require_subscription(bot, message) -> bool:
    if _is_subscribed(bot, message.from_user.id):
        return True
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("📢 Подписаться на канал", url=f"https://t.me/{CHANNEL_USERNAME.lstrip('@')}"),
        types.InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription"),
    )
    bot.reply_to(message, "🔔 Для использования бота необходимо подписаться на наш канал!", reply_markup=markup)
    return False


def _format_request_text(request: dict[str, Any], user_display: str | None = None) -> str:
    display = user_display or f"ID {request['user_id']}"
    lines = [
        "🆘 Заявка поддержки",
        f"ID: {request['id']}",
        f"Шаблон: {request['template_title']}",
        f"Пользователь: {display}",
    ]
    if request.get("release_name"):
        lines.append(f"🎵 Релиз: {request['release_name']}")
    lines.extend(
        [
            f"Статус: {request['status']}",
            f"Создано: {format_request_datetime(request['created_at'])}",
            "",
            f"Сообщение:\n{request['details']}",
        ]
    )
    return "\n".join(lines)


def _notify_admins(bot, request: dict[str, Any], user_display: str) -> None:
    text = _format_request_text(request, user_display=user_display)
    markup = _status_keyboard(request["id"], request["status"])
    for admin_id in PERMANENT_ADMINS:
        try:
            bot.send_message(admin_id, text, reply_markup=markup)
        except Exception as exc:
            logger.error("Failed to send support request %s to admin %s: %s", request["id"], admin_id, exc)


def _clear_next_steps(bot, chat_id: int, user_id: int) -> None:
    try:
        if not hasattr(bot, "next_step_backend") or not hasattr(bot.next_step_backend, "clear_handlers"):
            return
        backend = bot.next_step_backend
        backend.clear_handlers(chat_id)
        backend.clear_handlers((chat_id, user_id))
        backend.clear_handlers(user_id)
    except Exception:
        pass


def _prompt_template(bot, chat_id: int, user_id: int, template: dict[str, Any]) -> None:
    lines = [f"📝 {template['title']}", template["description"], "", "Отправьте одним сообщением по шаблону:"]
    lines.extend(f"{field}: ..." for field in template["fields"])
    if template.get("note"):
        lines.extend(["", template["note"]])
    message = bot.send_message(chat_id, "\n".join(lines), reply_markup=_cancel_keyboard())
    bot.register_next_step_handler(message, lambda next_message: _process_template_answer(bot, next_message, template["id"], user_id))


def _process_template_answer(bot, message, template_id: str, user_id: int) -> None:
    user_storage = _storage(bot, user_id)
    if user_storage.pop("_support_cancelled", None):
        bot.send_message(message.chat.id, "🚫 Заявка отменена.", reply_markup=_main_markup())
        return

    text = (getattr(message, "text", "") or "").strip()
    if text in MAIN_MENU_TEXTS:
        bot.reply_to(message, "🚫 Заявка отменена.", reply_markup=_main_markup())
        return
    if text.lower() in {"/cancel", "отмена", "cancel"}:
        bot.reply_to(message, "🚫 Заявка отменена.", reply_markup=_main_markup())
        return
    if not text:
        sent = bot.reply_to(message, "Пожалуйста, отправьте текстовое сообщение.", reply_markup=_cancel_keyboard())
        bot.register_next_step_handler(sent, lambda next_message: _process_template_answer(bot, next_message, template_id, user_id))
        return

    template = _template_by_id(template_id)
    if template is None:
        bot.reply_to(message, "❌ Шаблон не найден. Попробуйте снова.", reply_markup=_support_keyboard())
        return

    try:
        request = create_support_request(
            user_id=user_id,
            template_id=template["id"],
            template_title=template["title"],
            details=text,
            request_data={"source": "template", "fields": template["fields"]},
        )
    except Exception as exc:
        logger.error("Could not create support request for user %s: %s", user_id, exc)
        bot.reply_to(message, "❌ Ошибка при сохранении заявки. Попробуйте позже.")
        return

    if request is None:
        bot.reply_to(message, "❌ Ошибка подключения к базе данных.")
        return

    bot.reply_to(
        message,
        f"✅ Заявка «{template['title']}» принята. Текущий статус: принят.\n"
        "Мы уведомили администратора и сообщим об обновлениях.",
    )
    _notify_admins(bot, request, _display_user(message.from_user))


def _process_free_question(bot, message) -> None:
    user_storage = _storage(bot, message.from_user.id)
    if user_storage.pop("_support_cancelled", None):
        bot.send_message(message.chat.id, "🚫 Заявка отменена.", reply_markup=_main_markup())
        return

    text = (getattr(message, "text", "") or "").strip()
    if text in MAIN_MENU_TEXTS:
        bot.reply_to(message, "🚫 Заявка отменена.", reply_markup=_main_markup())
        return
    if text.lower() in {"/cancel", "отмена", "cancel"}:
        bot.reply_to(message, "🚫 Заявка отменена.", reply_markup=_main_markup())
        return
    if not text:
        sent = bot.reply_to(message, "Пожалуйста, отправьте текстовое сообщение.", reply_markup=_cancel_keyboard())
        bot.register_next_step_handler(sent, lambda next_message: _process_free_question(bot, next_message))
        return

    try:
        request = create_support_request(
            user_id=message.from_user.id,
            template_id="free_question",
            template_title="Свободный вопрос",
            details=text,
            request_data={"source": "free_question"},
        )
    except Exception as exc:
        logger.error("Could not create free support request for user %s: %s", message.from_user.id, exc)
        bot.reply_to(message, "❌ Ошибка при сохранении заявки. Попробуйте позже.")
        return

    if request is None:
        bot.reply_to(message, "❌ Ошибка подключения к базе данных.")
        return

    bot.reply_to(
        message,
        "✅ Ваш вопрос принят. Текущий статус: принят.\n"
        "Мы уведомили администратора и сообщим об обновлениях.",
    )
    _notify_admins(bot, request, _display_user(message.from_user))


def _support_summary() -> str:
    counts = get_support_status_counts()
    total = sum(counts.values())
    lines = [f"Всего: {total}"]
    for status in SUPPORT_REQUEST_STATUSES:
        lines.append(f"{status.title()}: {counts.get(status, 0)}")
    return "\n".join(lines)


def register_support_handlers(bot) -> None:
    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "❓ Помощь/вопросы")
    def handle_help(message):
        if not _require_subscription(bot, message):
            return
        help_text = (
            "❓ Помощь и поддержка\n\n"
            "Выберите готовый шаблон обращения или напишите менеджеру напрямую.\n"
            "Все заявки получают статусы: принят / требует уточнения / решен.\n\n"
            "💡 Команды:\n"
            "/start - главная страница\n"
            "/main - вернуться в меню\n"
            "/cancel - отмена текущего ввода\n"
            "/admin - панель администратора\n\n"
            f"⏰ Менеджер работает с {SUPPORT_HOURS}\n"
            "❗️ Формулируйте вопрос одним сообщением.\n"
            f"💬 Менеджер: {MANAGER_USERNAME}"
        )
        bot.reply_to(message, help_text, reply_markup=_support_keyboard())

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "📞 Поддержка")
    def handle_support(message):
        if not _require_subscription(bot, message):
            return
        text = (
            "📞 Поддержка TWAS Label Studio\n\n"
            f"⏰ Время работы: {SUPPORT_HOURS}\n"
            f"💬 Менеджер: {MANAGER_USERNAME}\n"
            f"👑 Владелец: {OWNER_USERNAME}\n\n"
            "⬇️ Можете выбрать готовый шаблон обращения ниже или написать менеджеру напрямую."
        )
        markup = _support_keyboard()
        markup.add(types.InlineKeyboardButton("👑 Связаться с владельцем", url=f"https://t.me/{OWNER_USERNAME.lstrip('@')}"))
        bot.reply_to(message, text, reply_markup=markup)

    @bot.message_handler(commands=["support"])
    def handle_support_command(message):
        if not _require_subscription(bot, message):
            return
        _storage(bot, message.from_user.id).pop("_support_cancelled", None)
        sent = bot.reply_to(
            message,
            "📞 Поддержка TWAS Label Studio\n\n"
            "Напишите ваш вопрос, и мы передадим его администраторам.\n"
            "Опишите проблему максимально подробно.\n\n"
            "Для отмены отправьте /cancel",
            reply_markup=_cancel_keyboard(),
        )
        bot.register_next_step_handler(sent, lambda next_message: _process_free_question(bot, next_message))

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "🆘 Мои заявки")
    def handle_my_support_requests(message):
        requests = list_user_support_requests(message.from_user.id)
        if not requests:
            bot.reply_to(message, "🆘 У вас пока нет заявок поддержки.")
            return

        lines = ["🆘 Ваши заявки поддержки:\n"]
        for request in requests:
            lines.append(
                f"• #{request['id']} {request['template_title']} | {request['status']} | "
                f"{format_request_datetime(request['created_at'])}"
            )
        lines.append("\nСтатусы обновляются автоматически. Если нужна новая заявка - выберите ее в разделе «Помощь» на главном экране.")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile"))
        bot.reply_to(message, "\n".join(lines), reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("support_template:"))
    def handle_support_template_selection(call):
        template = _template_by_id(call.data.split(":", 1)[1])
        if template is None:
            bot.answer_callback_query(call.id, "Шаблон недоступен.", show_alert=True)
            return
        _storage(bot, call.from_user.id).pop("_support_cancelled", None)
        bot.answer_callback_query(call.id)
        _prompt_template(bot, call.message.chat.id, call.from_user.id, template)

    @bot.callback_query_handler(func=lambda call: call.data == "support_cancel")
    def handle_support_cancel(call):
        user_id = call.from_user.id
        chat_id = call.message.chat.id
        _clear_next_steps(bot, chat_id, user_id)
        user_storage = _storage(bot, user_id)
        user_storage.pop("support_request_data", None)
        user_storage.pop("support_state", None)
        user_storage.pop("videoshot_state", None)
        user_storage["_support_cancelled"] = True
        bot.answer_callback_query(call.id, "Отменено")
        bot.send_message(chat_id, "🚫 Заявка отменена.", reply_markup=_main_markup())

    @bot.callback_query_handler(func=lambda call: call.data == "admin_support")
    def handle_admin_support_main(call):
        if not is_admin_user(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.")
            return
        text = "🆘 Раздел поддержки\n\n📩 Заявки поддержки:\n" f"{_support_summary()}\n\nВыберите, что посмотреть:"
        markup = types.InlineKeyboardMarkup(row_width=1)
        markup.add(types.InlineKeyboardButton("🆘 Список заявок поддержки", callback_data="admin_support_list"))
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "admin_support_list")
    def handle_admin_support_list(call):
        if not is_admin_user(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа.")
            return
        requests = list_recent_support_requests(limit=10)
        if not requests:
            text = "🆘 Заявок поддержки пока нет."
        else:
            lines = ["🆘 Заявки поддержки (последние 10):", ""]
            for request in requests:
                lines.append(
                    f"• #{request['id']} {request['template_title']} | {request['status']} | "
                    f"{format_request_datetime(request['created_at'])}"
                )
            lines.append("\nВыберите заявку для подробностей.")
            text = "\n".join(lines)

        markup = types.InlineKeyboardMarkup(row_width=1)
        for request in requests:
            markup.add(
                types.InlineKeyboardButton(
                    f"#{request['id']} {request['template_title']} ({request['status']})",
                    callback_data=f"support_detail_{request['id']}",
                )
            )
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_support"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("support_detail_"))
    def handle_admin_support_detail(call):
        if not is_admin_user(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа.")
            return
        try:
            request_id = int(call.data.split("_", 2)[2])
        except ValueError:
            bot.answer_callback_query(call.id, "Неверный ID заявки.", show_alert=True)
            return
        request = get_support_request(request_id)
        if request is None:
            bot.answer_callback_query(call.id, "Заявка не найдена.", show_alert=True)
            return
        markup = _status_keyboard(request["id"], request["status"])
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_support_list"))
        bot.edit_message_text(_format_request_text(request), call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("support_status:"))
    def handle_support_status_change(call):
        if not is_admin_user(call.from_user.id):
            bot.answer_callback_query(call.id, "У вас нет доступа.")
            return
        try:
            _, request_id_raw, new_status = call.data.split(":", 2)
            request_id = int(request_id_raw)
        except ValueError:
            bot.answer_callback_query(call.id, "Неверные данные", show_alert=True)
            return
        if new_status not in SUPPORT_REQUEST_STATUSES:
            bot.answer_callback_query(call.id, "Недопустимый статус", show_alert=True)
            return
        try:
            request = update_support_status(request_id, new_status)
        except Exception as exc:
            logger.error("Could not update support request %s status: %s", request_id, exc)
            bot.answer_callback_query(call.id, "Ошибка обновления статуса.", show_alert=True)
            return
        if request is None:
            bot.answer_callback_query(call.id, "Заявка не найдена", show_alert=True)
            return

        markup = _status_keyboard(request["id"], new_status)
        try:
            bot.edit_message_text(_format_request_text(request), call.message.chat.id, call.message.message_id, reply_markup=markup)
        except Exception as exc:
            logger.debug("Could not edit admin support message: %s", exc)

        try:
            bot.send_message(request["user_id"], f"ℹ️ Статус вашей заявки «{request['template_title']}» обновлен: {new_status}.")
        except Exception as exc:
            logger.error("Failed to notify user about support status: %s", exc)

        bot.answer_callback_query(call.id, f"Статус изменен на «{new_status}»")
