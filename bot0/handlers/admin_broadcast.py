"""Admin broadcast handlers."""
from __future__ import annotations

import logging

from telebot import types

from db.repositories.admins import ensure_admin_access
from db.repositories.broadcast import list_broadcast_recipients

logger = logging.getLogger(__name__)

BROADCAST_LEVELS = ("artist", "admin", "owner", "creator")


def _check_admin(bot, call) -> bool:
    try:
        allowed = ensure_admin_access(call.from_user.id, call.from_user.username).get("allowed")
    except Exception as exc:
        logger.error("Could not check admin broadcast access for user %s: %s", call.from_user.id, exc)
        allowed = False
    if not allowed:
        bot.answer_callback_query(call.id, "У вас нет доступа к этой функции", show_alert=True)
        return False
    return True


def _selected_levels(bot, user_id: int) -> list[str]:
    if not hasattr(bot, "broadcast_levels"):
        bot.broadcast_levels = {}
    return bot.broadcast_levels.setdefault(user_id, [])


def _broadcast_markup(selected: list[str]):
    markup = types.InlineKeyboardMarkup(row_width=2)
    for level in BROADCAST_LEVELS:
        is_selected = level in selected
        markup.add(types.InlineKeyboardButton(f"{'✅' if is_selected else '❌'} {level}", callback_data=f"broadcast_level_{level}"))
    markup.add(
        types.InlineKeyboardButton("✏️ Создать рассылку", callback_data="broadcast_create"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="admin_back"),
    )
    return markup


def _show_broadcast_menu(bot, call) -> None:
    selected = _selected_levels(bot, call.from_user.id)
    bot.edit_message_text(
        "Выберите уровни пользователей для рассылки:",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=_broadcast_markup(selected),
    )


def _process_broadcast_message(bot, message) -> None:
    user_id = message.from_user.id
    broadcast_text = (message.text or "").strip()
    if not broadcast_text:
        bot.reply_to(message, "❌ Сообщение не может быть пустым. Попробуйте снова.")
        bot.register_next_step_handler(message, lambda next_message: _process_broadcast_message(bot, next_message))
        return

    selected = _selected_levels(bot, user_id)
    if not selected:
        bot.send_message(user_id, "❌ Не выбраны уровни для рассылки. Пожалуйста, выберите хотя бы один уровень.")
        return

    total_sent = 0
    total_skipped = 0
    detailed_log: list[str] = []

    try:
        users = list_broadcast_recipients()
        for user in users:
            user_id_db = user["telegram_id"]
            active_roles = [role for role, active in user["roles"].items() if active == 1]
            if not any(role in selected for role in active_roles):
                total_skipped += 1
                detailed_log.append(f"⏩ Пропущено {user_id_db}: нет совпадения ролей")
                continue
            try:
                bot.send_message(user_id_db, broadcast_text)
                total_sent += 1
                detailed_log.append(f"✅ Отправлено {user_id_db} (роли: {', '.join(active_roles)})")
            except Exception as send_error:
                total_skipped += 1
                detailed_log.append(f"❌ Не отправлено {user_id_db}: {send_error}")

        report_text = (
            "📢 Рассылка завершена:\n"
            f"✅ Отправлено: {total_sent}\n"
            f"❌ Не отправлено: {total_skipped}\n"
            f"Уровни: {', '.join(selected)}\n\n"
            "Подробности:\n" + "\n".join(detailed_log[:20])
        )
        bot.send_message(message.from_user.id, report_text)
    except Exception as exc:
        logger.error("CRITICAL error in broadcast: %s", exc)
        bot.send_message(message.from_user.id, f"❌ Произошла критическая ошибка при рассылке: {exc}")


def register_admin_broadcast_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "admin_broadcast")
    def open_admin_broadcast(call):
        if not _check_admin(bot, call):
            return
        bot.answer_callback_query(call.id)
        _show_broadcast_menu(bot, call)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("broadcast_level_"))
    def toggle_broadcast_level(call):
        if not _check_admin(bot, call):
            return
        selected = _selected_levels(bot, call.from_user.id)
        level = call.data.split("_")[2]
        if level in selected:
            selected.remove(level)
        else:
            selected.append(level)
        bot.answer_callback_query(call.id)
        _show_broadcast_menu(bot, call)

    @bot.callback_query_handler(func=lambda call: call.data == "broadcast_create")
    def start_broadcast_message(call):
        if not _check_admin(bot, call):
            return
        selected = _selected_levels(bot, call.from_user.id)
        if not selected:
            bot.answer_callback_query(call.id, "❌ Сначала выберите уровни пользователей!", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text("Введите сообщение для рассылки:", call.message.chat.id, call.message.message_id)
        bot.register_next_step_handler(call.message, lambda message: _process_broadcast_message(bot, message))
