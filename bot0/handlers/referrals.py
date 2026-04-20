"""Referral profile handlers for the modular bot."""
from __future__ import annotations

import logging
from decimal import Decimal
from urllib.parse import quote

from telebot import types

from core.config import BOT_USERNAME
from db.repositories.referrals import get_or_create_referral_summary


logger = logging.getLogger(__name__)


def _money(value) -> str:
    amount = Decimal(value or 0)
    if amount == amount.to_integral_value():
        return f"{int(amount)}₽"
    return f"{amount:.2f}₽"


def _referral_link(code: str) -> str:
    return f"https://t.me/{BOT_USERNAME.lstrip('@')}?start={code}"


def _markup(code: str):
    link = _referral_link(code)
    share_text = f"Присоединяйся к TWAS Label!\n\n{link}"
    share_url = f"https://t.me/share/url?url={quote(link)}&text={quote(share_text)}"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("📤 Поделиться ссылкой", url=share_url))
    markup.add(types.InlineKeyboardButton("📊 Статистика", callback_data="referral_stats"))
    markup.add(types.InlineKeyboardButton("📋 Показать ссылку", callback_data=f"copy_referral_{code}"))
    markup.add(types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile"))
    return markup


def _text(summary: dict) -> str:
    code = summary["referral_code"]
    return (
        "👥 Пригласите друзей и получайте бонусы!\n\n"
        f"🔗 Ваша реферальная ссылка:\n`{_referral_link(code)}`\n\n"
        "📊 Статистика:\n"
        f"👥 Приглашено друзей: {summary['referral_count']}\n"
        f"💰 Заработано: {_money(summary['referral_earnings'])}\n\n"
        "💡 Как это работает:\n"
        "• Отправьте ссылку другу\n"
        "• Друг регистрируется по ссылке\n"
        "• Вы получаете 100₽ на баланс\n"
        "• Друг получает 50₽ на баланс"
    )


def _stats_text(summary: dict) -> str:
    return (
        "📊 Детальная статистика рефералов:\n\n"
        f"🔗 Код: `{summary['referral_code']}`\n"
        f"👥 Всего приглашено: {summary['total_referrals']}\n"
        f"✅ Активных: {summary['active_referrals']}\n"
        f"💰 Заработано: {_money(summary['referral_earnings'])}"
    )


def _load_summary(user_id: int) -> dict | None:
    try:
        return get_or_create_referral_summary(user_id)
    except Exception as exc:
        logger.error("Could not load referral summary for user %s: %s", user_id, exc)
        return None


def register_referral_handlers(bot) -> None:
    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "👥 Пригласи друга")
    def handle_invite_friend(message):
        summary = _load_summary(message.from_user.id)
        if summary is None:
            bot.reply_to(message, "❌ Ошибка при получении реферальной информации.")
            return
        bot.reply_to(message, _text(summary), reply_markup=_markup(summary["referral_code"]), parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data == "profile_referral")
    def handle_profile_referral(call):
        summary = _load_summary(call.from_user.id)
        if summary is None:
            bot.answer_callback_query(call.id, "❌ Ошибка при получении реферальной информации", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _text(summary),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_markup(summary["referral_code"]),
            parse_mode="Markdown",
        )

    @bot.callback_query_handler(func=lambda call: call.data == "referral_stats")
    def handle_referral_stats(call):
        summary = _load_summary(call.from_user.id)
        if summary is None:
            bot.answer_callback_query(call.id, "❌ Ошибка при получении статистики", show_alert=True)
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("👥 Пригласить друга", callback_data="profile_referral"))
        markup.add(types.InlineKeyboardButton("◀️ Назад в профиль", callback_data="back_to_profile"))
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _stats_text(summary),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
            parse_mode="Markdown",
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("copy_referral_"))
    def handle_copy_referral(call):
        code = call.data.replace("copy_referral_", "", 1)
        bot.answer_callback_query(call.id, "Ссылка показана в сообщении")
        bot.send_message(call.message.chat.id, f"🔗 Ваша реферальная ссылка:\n{_referral_link(code)}")
