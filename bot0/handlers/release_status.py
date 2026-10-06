"""Release status menu and write handlers."""
from __future__ import annotations

import json
import logging

from telebot import types

from db.repositories.account_connections import notification_chat_id
from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.release_details import (
    get_album_detail,
    get_release_detail,
    get_release_status_notification,
    get_release_upc,
    update_release_status,
    update_release_upc,
)
from db.repositories.users import list_admin_ids
from handlers.release_details import (
    _album_detail_markup,
    _album_detail_text,
    _release_detail_markup,
    _release_detail_text,
)


from utils.statuses import release_status_label

logger = logging.getLogger(__name__)

RELEASE_STATUSES = [
    "принят",
    "отправлен на площадки",
    "отгружен на площадки",
    "Релиз",
    "Отозван с площадок",
]


def _is_admin(user_id: int) -> bool:
    if user_id in PERMANENT_ADMINS or user_id in ADMIN_IDS:
        return True
    try:
        return user_id in list_admin_ids()
    except Exception as exc:
        logger.error("Could not check admin status for user %s: %s", user_id, exc)
        return False


def _status_selection_markup(release_id: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for status in RELEASE_STATUSES:
        markup.add(types.InlineKeyboardButton(f"🔄 {status.capitalize()}", callback_data=f"status_update_{release_id}_{status}"))
    return markup


def _album_status_selection_markup(album_id: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for status in RELEASE_STATUSES:
        markup.add(types.InlineKeyboardButton(f"🔄 {status.capitalize()}", callback_data=f"album_status_confirm_{album_id}_{status}"))
    markup.add(types.InlineKeyboardButton("◀️ Назад к альбому", callback_data=f"album_detail_{album_id}_admin"))
    return markup


def _status_notification_text(info: dict, new_status: str) -> str:
    message = (
        "🔄 Статус вашего релиза обновлен!\n\n"
        f"🎵 Релиз: {info.get('release_name')}\n"
        f"🆕 Новый статус: {release_status_label(new_status)}\n\n"
    )
    platform_links = info.get("platform_links")
    if new_status.lower() == "релиз" and platform_links:
        try:
            links_data = platform_links
            if isinstance(platform_links, str):
                links_data = json.loads(platform_links)
            if links_data and isinstance(links_data, dict):
                message += "🎧 Ваш релиз доступен на площадках:\n\n"
                for platform_name, platform_url in links_data.items():
                    if platform_url and str(platform_url).strip():
                        message += f"• {platform_name}: {platform_url}\n"
                message += "\n🎉 Поздравляем с релизом!"
        except Exception as exc:
            logger.warning("Could not parse platform_links for release status notification: %s", exc)
    return message


def _notify_user_about_status_change(bot, release_id: int, new_status: str) -> None:
    info = get_release_status_notification(release_id)
    if not info:
        return
    telegram_id = notification_chat_id(info.get("user_id"))
    if not telegram_id:
        return
    try:
        bot.send_message(telegram_id, _status_notification_text(info, new_status))
        logger.info("Notified user %s about release %s status change to %r", telegram_id, release_id, new_status)
    except Exception as exc:
        logger.error("Failed to notify user %s about release %s status change: %s", telegram_id, release_id, exc)


def _show_admin_release_detail(bot, call, release_id: int) -> None:
    release = get_release_detail(release_id)
    if not release:
        bot.answer_callback_query(call.id, "❌ Релиз не найден", show_alert=True)
        return
    bot.edit_message_text(
        _release_detail_text(release),
        call.message.chat.id,
        call.message.message_id,
        reply_markup=_release_detail_markup(release, admin_mode=True),
    )


def _show_admin_album_detail(bot, call, album_id: int) -> None:
    album = get_album_detail(album_id)
    if not album:
        bot.answer_callback_query(call.id, "❌ Альбом не найден", show_alert=True)
        return
    bot.edit_message_text(
        f"<code>{_album_detail_text(album)}</code>",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=_album_detail_markup(album, admin_mode=True),
    )


def _status_keyboard_for_action(release_id: int, action: str | None = None):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if action == "approve":
        markup.add(types.InlineKeyboardButton("✅ Принят", callback_data=f"status_update_{release_id}_принят"))
    elif action == "reject":
        markup.add(types.InlineKeyboardButton("❌ Отклонен", callback_data=f"status_update_{release_id}_отклонен"))
    for status in RELEASE_STATUSES:
        if status not in {"принят", "отклонен"}:
            markup.add(types.InlineKeyboardButton(f"🔄 {status.capitalize()}", callback_data=f"status_update_{release_id}_{status}"))
    return markup


def register_release_status_handlers(bot) -> None:
    def process_release_id_for_status(message, action: str | None = None):
        try:
            release_id = int(message.text)
            bot.send_message(
                message.chat.id,
                "Выберите новый статус релиза:",
                reply_markup=_status_keyboard_for_action(release_id, action),
            )
        except ValueError:
            msg = bot.send_message(message.chat.id, "❌ Неверный формат ID. Введите число:")
            bot.register_next_step_handler(msg, process_release_id_for_status, action)

    @bot.callback_query_handler(func=lambda call: call.data in {"releases_approve", "releases_reject"})
    def handle_release_status_change(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут изменять статус", show_alert=True)
            return
        action = "approve" if call.data == "releases_approve" else "reject"
        bot.edit_message_text(
            "Введите ID релиза:",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.register_next_step_handler(call.message, process_release_id_for_status, action)

    @bot.callback_query_handler(func=lambda call: call.data == "releases_change_status")
    def handle_change_status(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут изменять статус", show_alert=True)
            return
        bot.edit_message_text(
            "Введите ID релиза для изменения статуса:",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.register_next_step_handler(call.message, process_release_id_for_status)

    def process_upc_update(message, release_id: int, album_mode: bool = False):
        if not _is_admin(message.from_user.id):
            bot.reply_to(message, "❌ Только администраторы могут изменять UPC-код")
            return
        new_upc = (message.text or "").strip()
        if not new_upc:
            bot.reply_to(message, "❌ UPC код не может быть пустым")
            return
        try:
            updated = update_release_upc(release_id, new_upc)
        except Exception as exc:
            logger.error("Error updating UPC code for release %s: %s", release_id, exc)
            bot.reply_to(message, "❌ Ошибка при обновлении UPC кода")
            return
        if not updated:
            bot.reply_to(message, "❌ Релиз не найден")
            return
        back_callback = f"album_detail_{release_id}_admin" if album_mode else f"my_release_detail_{release_id}_admin"
        back_text = "◀️ Назад к альбому" if album_mode else "◀️ Назад к релизу"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(back_text, callback_data=back_callback))
        suffix = " альбома" if album_mode else ""
        bot.send_message(message.chat.id, f"✅ UPC код{suffix} успешно обновлен на: {new_upc}", reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("change_upc_"))
    def handle_change_upc_request(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут изменять UPC-код", show_alert=True)
            return
        try:
            release_id = int(call.data.split("_")[2])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return
        bot.edit_message_text(
            "✏️ Введите новый UPC код для релиза:",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.register_next_step_handler(call.message, process_upc_update, release_id, False)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("album_upc_update_"))
    def handle_album_upc_update(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут изменять UPC код", show_alert=True)
            return
        try:
            album_id = int(call.data.split("_")[3])
            current_upc = get_release_upc(album_id) or "пока что нет"
        except Exception as exc:
            logger.error("Error opening album UPC update: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад к альбому", callback_data=f"album_detail_{album_id}_admin"))
        bot.edit_message_text(
            f"🏷️ Текущий UPC код альбома: {current_upc}\n\nВведите новый UPC код для альбома:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
        bot.register_next_step_handler(call.message, process_upc_update, album_id, True)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("change_status_"))
    def handle_change_status_request(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут изменять статус", show_alert=True)
            return
        try:
            release_id = int(call.data.split("_")[2])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            f"Выберите новый статус для релиза ID {release_id}:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_status_selection_markup(release_id),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("status_update_"))
    def handle_status_update(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут изменять статус", show_alert=True)
            return
        try:
            parts = call.data.split("_")
            release_id = int(parts[2])
            new_status = "_".join(parts[3:])
            if not new_status:
                raise ValueError("empty status")
            updated = update_release_status(release_id, new_status)
        except Exception as exc:
            logger.error("Error updating release status: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return

        if not updated:
            bot.answer_callback_query(call.id, "❌ Ошибка при обновлении статуса", show_alert=True)
            return

        _notify_user_about_status_change(bot, release_id, new_status)
        bot.answer_callback_query(call.id, f"✅ Статус обновлен на: {new_status}", show_alert=True)
        _show_admin_release_detail(bot, call, release_id)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("album_status_update_"))
    def handle_album_status_update(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут изменять статус", show_alert=True)
            return

        try:
            album_id = int(call.data.split("_")[3])
        except (ValueError, IndexError):
            bot.answer_callback_query(call.id, "❌ Ошибка данных", show_alert=True)
            return

        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🔄 Выберите новый статус для альбома:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_album_status_selection_markup(album_id),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("album_status_confirm_"))
    def handle_album_status_confirm(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Только администраторы могут изменять статус", show_alert=True)
            return
        try:
            parts = call.data.split("_")
            album_id = int(parts[3])
            new_status = "_".join(parts[4:])
            if not new_status:
                raise ValueError("empty status")
            updated = update_release_status(album_id, new_status)
        except Exception as exc:
            logger.error("Error updating album status: %s", exc)
            bot.answer_callback_query(call.id, f"❌ Ошибка: {exc}", show_alert=True)
            return

        if not updated:
            bot.answer_callback_query(call.id, "❌ Ошибка при обновлении статуса альбома", show_alert=True)
            return

        _notify_user_about_status_change(bot, album_id, new_status)
        bot.answer_callback_query(call.id, f"✅ Статус альбома обновлен на: {new_status}", show_alert=True)
        _show_admin_album_detail(bot, call, album_id)
