"""Read-only release platform link handlers."""
from __future__ import annotations

import logging
from datetime import datetime

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.release_links import (
    add_release_platform_link,
    clear_release_platform_links,
    edit_release_platform_link,
    get_release_back_callback,
    get_release_platform_links,
)
from db.repositories.users import list_admin_ids


logger = logging.getLogger(__name__)


def _is_admin(user_id: int) -> bool:
    if user_id in PERMANENT_ADMINS or user_id in ADMIN_IDS:
        return True
    try:
        return user_id in list_admin_ids()
    except Exception as exc:
        logger.error("Could not check admin status for user %s: %s", user_id, exc)
        return False


def _platform_links_text(links: dict) -> str:
    if not links:
        return "🔗 Информация не добавлена"
    lines = ["🔗 Добавленная информация:", ""]
    for platform, value in links.items():
        lines.append(f"📱 {platform}: {value}")
    return "\n".join(lines)


def _back_markup(back_callback: str):
    back_text = "◀️ Назад к альбому" if "album_detail" in back_callback else "◀️ Назад к релизу"
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(back_text, callback_data=back_callback))
    return markup


def _link_management_markup(release_id: int, back_callback: str):
    back_text = "◀️ Назад к альбому" if "album_detail" in back_callback else "◀️ Назад к релизу"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Добавить информацию", callback_data=f"add_platform_link_{release_id}"),
        types.InlineKeyboardButton("📝 Редактировать информацию", callback_data=f"edit_platform_links_{release_id}"),
        types.InlineKeyboardButton("❌ Удалить информацию", callback_data=f"delete_platform_links_{release_id}"),
        types.InlineKeyboardButton("👁️ Просмотреть информацию", callback_data=f"view_platform_links_{release_id}"),
        types.InlineKeyboardButton(back_text, callback_data=back_callback),
    )
    return markup


def _prompt_platform_link(bot, chat_id: int, release_id: int):
    instructions = (
        "🔗 Отправьте новую ссылку или информацию о площадке.\n\n"
        "Формат (рекомендуется):\n"
        "Площадка|https://example.com/...\n\n"
        "Можно отправить любой текст, если требуется заметка."
    )
    msg = bot.send_message(chat_id, instructions)
    bot.register_next_step_handler(msg, _process_add_platform_link(bot), release_id)


def _process_add_platform_link(bot):
    def process_add_platform_link(message, release_id: int):
        if not _is_admin(message.from_user.id):
            bot.reply_to(message, "❌ Только администраторы могут добавлять информацию о площадках")
            return
        try:
            platform_name, platform_info = add_release_platform_link(
                int(release_id),
                message.text or "",
                datetime.now().strftime("%H:%M"),
            )
            back_callback = get_release_back_callback(int(release_id))
            back_text = "◀️ Назад к альбому" if "album_detail" in back_callback else "◀️ Назад к релизу"
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(back_text, callback_data=back_callback))
            bot.reply_to(
                message,
                "✅ Информация добавлена!\n\n"
                f"Название: {platform_name}\n"
                f"Содержание: {platform_info}",
                reply_markup=markup,
            )
        except Exception as exc:
            logger.error("Error processing platform information: %s", exc)
            bot.reply_to(message, f"❌ Ошибка: {exc}")
    return process_add_platform_link


def _process_edit_platform_link(bot):
    def process_edit_platform_link(message, release_id: int, platform_name: str):
        if not _is_admin(message.from_user.id):
            bot.reply_to(message, "❌ Только администраторы могут редактировать информацию о площадках")
            return
        try:
            new_value = edit_release_platform_link(int(release_id), platform_name, message.text or "")
            back_callback = get_release_back_callback(int(release_id))
            back_text = "◀️ Назад к альбому" if "album_detail" in back_callback else "◀️ Назад к релизу"
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton(back_text, callback_data=back_callback))
            bot.reply_to(
                message,
                f"✅ Информация для площадки {platform_name} обновлена!\n\nНовая информация: {new_value}",
                reply_markup=markup,
            )
        except Exception as exc:
            logger.error("Error processing platform information edit: %s", exc)
            bot.reply_to(message, f"❌ Ошибка: {exc}")
    return process_edit_platform_link


def register_release_link_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data.startswith("manage_platform_links_"))
    def handle_manage_platform_links_request(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(
                call.id,
                "❌ Только администраторы могут управлять информацией о площадках",
                show_alert=True,
            )
            return

        try:
            release_id = int(call.data.split("_")[3])
            back_callback = get_release_back_callback(release_id)
        except Exception as exc:
            logger.error("Error opening platform link menu: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🔗 Управление ссылками\n\nВыберите действие:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_link_management_markup(release_id, back_callback),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("view_platform_links_"))
    def handle_view_platform_links_request(call):
        try:
            release_id = int(call.data.split("_")[3])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return

        try:
            links = get_release_platform_links(release_id)
            back_callback = get_release_back_callback(release_id)
        except Exception as exc:
            logger.error("Error viewing platform information for release %s: %s", release_id, exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _platform_links_text(links),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_back_markup(back_callback),
        )


    @bot.callback_query_handler(func=lambda call: call.data.startswith("add_platform_link_"))
    def handle_add_platform_link_request(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут добавлять информацию о площадках", show_alert=True)
            return
        try:
            release_id = int(call.data.split("_")[3])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return
        bot.edit_message_text(
            "🔗 Добавление информации о площадке\n\n"
            "Введите любую информацию в любом формате:\n\n"
            "Примеры:\n"
            "• Spotify|https://open.spotify.com/track/...\n"
            "• VK|ID: 123456789\n"
            "• Telegram|@channel_name\n"
            "• Примечания|Любая дополнительная информация\n"
            "• Просто текст без разделителей",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.register_next_step_handler(call.message, _process_add_platform_link(bot), release_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("quick_link_menu_"))
    def handle_quick_link_menu(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Недостаточно прав", show_alert=True)
            return
        try:
            release_id = int(call.data.split("_")[-1])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return
        bot.answer_callback_query(call.id, "✏️ Отправьте новую ссылку сообщением")
        _prompt_platform_link(bot, call.message.chat.id, release_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("edit_platform_links_"))
    def handle_edit_platform_links_request(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут редактировать информацию о площадках", show_alert=True)
            return
        try:
            release_id = int(call.data.split("_")[3])
            platform_links = get_release_platform_links(release_id)
            back_callback = get_release_back_callback(release_id)
        except Exception as exc:
            logger.error("Error editing platform information: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return

        back_text = "◀️ Назад к альбому" if "album_detail" in back_callback else "◀️ Назад к релизу"
        markup = types.InlineKeyboardMarkup(row_width=1)
        if platform_links:
            for platform in platform_links.keys():
                markup.add(types.InlineKeyboardButton(f"✏️ {platform}", callback_data=f"edit_platform_{release_id}_{platform}"))
            markup.add(types.InlineKeyboardButton(back_text, callback_data=back_callback))
            text = "✏️ Редактирование информации\n\nВыберите элемент для редактирования:"
        else:
            markup.add(types.InlineKeyboardButton(back_text, callback_data=back_callback))
            text = "🔗 Информация не добавлена\n\nСначала добавьте информацию."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith("edit_platform_") and not call.data.startswith("edit_platform_links_")
    )
    def handle_edit_specific_platform_request(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут редактировать информацию о площадках", show_alert=True)
            return
        try:
            _, _, release_id, platform_name = call.data.split("_", 3)
            int(release_id)
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return
        bot.edit_message_text(
            f"✏️ Редактирование информации: {platform_name}\n\n"
            "Введите новую информацию в любом формате:\n"
            "• Текст\n• Ссылки\n• Многострочный текст\n• Любые символы и эмодзи 🎵🎤🎹",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.register_next_step_handler(call.message, _process_edit_platform_link(bot), int(release_id), platform_name)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("delete_platform_links_"))
    def handle_delete_platform_links_request(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут удалять информацию о площадках", show_alert=True)
            return
        try:
            release_id = int(call.data.split("_")[3])
            clear_release_platform_links(release_id)
            back_callback = get_release_back_callback(release_id)
        except Exception as exc:
            logger.error("Error deleting platform information: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return
        back_text = "◀️ Назад к альбому" if "album_detail" in back_callback else "◀️ Назад к релизу"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(back_text, callback_data=back_callback))
        bot.edit_message_text("✅ Вся информация удалена!", call.message.chat.id, call.message.message_id, reply_markup=markup)
