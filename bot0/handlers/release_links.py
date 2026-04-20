"""Read-only release platform link handlers."""
from __future__ import annotations

import logging

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.release_links import get_release_back_callback, get_release_platform_links
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
