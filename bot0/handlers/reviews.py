"""Review handlers for the modular bot."""
from __future__ import annotations

import logging
from datetime import datetime
from html import escape
from typing import Any

from telebot import types

from db.repositories.reviews import (
    approve_review,
    count_pending_reviews,
    create_review,
    delete_review,
    get_random_approved_review,
    get_review_detail,
    list_approved_reviews,
    list_reviews_for_admin,
)
from db.repositories.users import list_admin_ids


logger = logging.getLogger(__name__)

REVIEW_CATEGORIES = {
    "distribution": "🎵 Дистрибуция",
    "design": "🎨 Обложки + Motion",
    "izba": "IZBA Records",
    "all": "⭐️ Все отзывы",
}


def _state(bot) -> dict[int, dict[str, Any]]:
    if not hasattr(bot, "review_state"):
        bot.review_state = {}
    return bot.review_state


def _format_date(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y")
    return "Дата неизвестна"


def _stars(rating: int) -> str:
    return "⭐️" * max(0, min(int(rating or 0), 5))


def _main_menu_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("👀 Посмотреть отзывы", callback_data="reviews_view_menu"),
        types.InlineKeyboardButton("✍️ Оставить отзыв", callback_data="reviews_create_menu"),
    )
    return markup


def _create_menu_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    for key in ("distribution", "design", "izba"):
        markup.add(types.InlineKeyboardButton(REVIEW_CATEGORIES[key], callback_data=f"review_create_{key}"))
    markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="reviews_back_main"))
    return markup


def _view_menu_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(REVIEW_CATEGORIES["distribution"], callback_data="reviews_category_distribution"),
        types.InlineKeyboardButton(REVIEW_CATEGORIES["design"], callback_data="reviews_category_design"),
        types.InlineKeyboardButton("🔄 Случайный отзыв", callback_data="reviews_random"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="reviews_back_main"),
    )
    return markup


def _rating_markup():
    markup = types.InlineKeyboardMarkup(row_width=5)
    markup.add(*[types.InlineKeyboardButton(f"{i}⭐️", callback_data=f"rating_{i}") for i in range(1, 6)])
    return markup


def _moderation_markup(review_id: int):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f"review_approve_{review_id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"review_reject_{review_id}"),
    )
    return markup


def _admin_reviews_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("⏳ Ждут одобрения", callback_data="admin_reviews_pending"),
        types.InlineKeyboardButton("📚 Все отзывы", callback_data="admin_reviews_all"),
    )
    return markup


def _send_or_edit(bot, message, text: str, reply_markup=None) -> None:
    if getattr(message, "message_id", None):
        bot.edit_message_text(text, message.chat.id, message.message_id, reply_markup=reply_markup)
    else:
        bot.send_message(message.chat.id, text, reply_markup=reply_markup)


def _notify_admins_about_review(bot, review_id: int) -> None:
    review = get_review_detail(review_id)
    if not review:
        logger.error("Review %s not found for admin notification", review_id)
        return

    text = (
        "📝 Новый отзыв на модерацию!\n\n"
        f"👤 Артист: {escape(str(review.get('name') or 'Без имени'))} (@{escape(str(review.get('tg') or ''))})\n"
        f"📂 Услуга: {escape(str(review.get('service_type') or ''))}\n"
        f"⭐️ Оценка: {_stars(review.get('rating') or 0)}\n"
        f"💬 Текст: {escape(str(review.get('text') or ''))[:500]}"
    )
    for admin_id in list_admin_ids():
        try:
            bot.send_message(admin_id, text, reply_markup=_moderation_markup(review_id))
        except Exception as exc:
            logger.error("Failed to notify admin %s about review %s: %s", admin_id, review_id, exc)


def register_reviews_handlers(bot) -> None:
    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "⭐️ Отзывы")
    def handle_reviews_menu(message):
        bot.reply_to(message, "⭐️ Отзывы\n\nВыберите действие:", reply_markup=_main_menu_markup())

    @bot.callback_query_handler(func=lambda call: call.data == "reviews_create_menu")
    def handle_reviews_create_menu(call):
        bot.edit_message_text("📝 Выберите категорию для отзыва:", call.message.chat.id, call.message.message_id, reply_markup=_create_menu_markup())

    @bot.callback_query_handler(func=lambda call: call.data.startswith("review_create_"))
    def start_review_creation(call):
        category = call.data.replace("review_create_", "", 1)
        if category not in REVIEW_CATEGORIES or category == "all":
            bot.answer_callback_query(call.id, "❌ Неверная категория", show_alert=True)
            return
        _state(bot)[call.from_user.id] = {"category": category}
        bot.edit_message_text(
            f"⭐️ Оцените услугу '{REVIEW_CATEGORIES[category]}' от 1 до 5:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_rating_markup(),
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("rating_"))
    def handle_rating(call):
        try:
            rating = int(call.data.split("_", 1)[1])
        except (IndexError, ValueError):
            bot.answer_callback_query(call.id, "❌ Неверная оценка", show_alert=True)
            return
        user_state = _state(bot).setdefault(call.from_user.id, {})
        user_state["rating"] = rating
        bot.edit_message_text(
            f"⭐️ Вы поставили {rating}.\n\n📝 Теперь напишите текст вашего отзыва:",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.register_next_step_handler(call.message, save_review)

    def save_review(message):
        text = (getattr(message, "text", "") or "").strip()
        user_id = message.from_user.id
        user_state = _state(bot).get(user_id, {})
        category = user_state.get("category")
        rating = user_state.get("rating")

        if not category or not rating:
            bot.reply_to(message, "❌ Данные отзыва потеряны. Начните заново.")
            return
        if not text:
            bot.reply_to(message, "❌ Текст отзыва не может быть пустым. Напишите отзыв:")
            bot.register_next_step_handler(message, save_review)
            return

        try:
            review_id = create_review(user_id, category, int(rating), text)
        except Exception as exc:
            logger.error("Error saving review for user %s: %s", user_id, exc)
            bot.reply_to(message, "❌ Не удалось сохранить отзыв. Попробуйте позже.")
            return

        _state(bot).pop(user_id, None)
        if review_id:
            _notify_admins_about_review(bot, review_id)
        bot.reply_to(message, "✅ Спасибо за отзыв! Он будет опубликован после проверки модератором.")

    @bot.callback_query_handler(func=lambda call: call.data == "reviews_view_menu")
    def handle_reviews_view_menu(call):
        bot.edit_message_text("📂 Выберите категорию отзывов:", call.message.chat.id, call.message.message_id, reply_markup=_view_menu_markup())

    @bot.callback_query_handler(func=lambda call: call.data.startswith("reviews_category_"))
    def handle_reviews_category(call):
        category = call.data.replace("reviews_category_", "", 1)
        if category not in REVIEW_CATEGORIES:
            bot.answer_callback_query(call.id, "❌ Неверная категория", show_alert=True)
            return
        reviews = list_approved_reviews(category, limit=10)
        category_name = REVIEW_CATEGORIES[category]
        if not reviews:
            text = f"😔 В категории {category_name} пока нет отзывов"
        else:
            lines = [f"⭐️ Последние отзывы ({category_name}):", ""]
            for review in reviews:
                body = str(review.get("text") or "")
                if len(body) > 200:
                    body = body[:200] + "..."
                lines.extend(
                    [
                        f"👤 {review.get('name') or 'Без имени'}",
                        _stars(review.get("rating") or 0),
                        f"💬 {body}",
                        f"📅 {_format_date(review.get('created_date'))}",
                        "",
                    ]
                )
            text = "\n".join(lines)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад к категориям", callback_data="reviews_back"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "reviews_random")
    def handle_reviews_random(call):
        review = get_random_approved_review()
        if not review:
            text = "😔 Пока нет отзывов"
        else:
            text = (
                f"🎵 Отзыв о {review.get('service_type')}\n\n"
                f"👤 {review.get('name') or 'Без имени'}\n"
                f"{_stars(review.get('rating') or 0)}\n"
                f"💭 {review.get('text') or ''}\n"
                f"📅 {_format_date(review.get('created_date'))}"
            )
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🔄 Еще отзыв", callback_data="reviews_random"),
            types.InlineKeyboardButton("◀️ Назад", callback_data="reviews_back_main"),
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data == "reviews_back")
    def handle_reviews_back(call):
        bot.edit_message_text("📂 Выберите категорию отзывов:", call.message.chat.id, call.message.message_id, reply_markup=_view_menu_markup())

    @bot.callback_query_handler(func=lambda call: call.data == "reviews_back_main")
    def handle_reviews_back_main(call):
        bot.edit_message_text("⭐️ Отзывы\n\nВыберите действие:", call.message.chat.id, call.message.message_id, reply_markup=_main_menu_markup())

    @bot.callback_query_handler(func=lambda call: call.data == "admin_reviews")
    def handle_admin_reviews(call):
        pending = count_pending_reviews()
        bot.edit_message_text(
            f"📝 Управление отзывами\n\n⏳ Ждут одобрения: {pending}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_admin_reviews_markup(),
        )

    @bot.callback_query_handler(func=lambda call: call.data in ("admin_reviews_pending", "admin_reviews_all"))
    def handle_admin_reviews_list(call):
        pending_only = call.data == "admin_reviews_pending"
        reviews = list_reviews_for_admin(pending_only=pending_only, limit=20)
        title = "⏳ Отзывы на модерации" if pending_only else "📚 Все отзывы"
        if not reviews:
            text = f"{title}\n\nСписок пуст."
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_reviews"))
        else:
            lines = [title, ""]
            markup = types.InlineKeyboardMarkup(row_width=1)
            for review in reviews:
                body = str(review.get("text") or "")
                if len(body) > 90:
                    body = body[:90] + "..."
                lines.extend(
                    [
                        f"ID: {review['id']} • {review.get('status')}",
                        f"👤 {review.get('name') or 'Без имени'}",
                        f"{_stars(review.get('rating') or 0)} {review.get('service_type')}",
                        f"💬 {body}",
                        "",
                    ]
                )
                markup.add(types.InlineKeyboardButton(f"Открыть #{review['id']}", callback_data=f"admin_review_detail_{review['id']}"))
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="admin_reviews"))
            text = "\n".join(lines)
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("admin_review_detail_"))
    def handle_admin_review_detail(call):
        try:
            review_id = int(call.data.replace("admin_review_detail_", "", 1))
        except ValueError:
            bot.answer_callback_query(call.id, "❌ Неверный ID", show_alert=True)
            return
        review = get_review_detail(review_id)
        if not review:
            bot.answer_callback_query(call.id, "❌ Отзыв не найден", show_alert=True)
            return
        text = (
            "📝 Полный текст отзыва\n\n"
            f"👤 Автор: {review.get('name') or 'Без имени'} (@{review.get('tg') or ''})\n"
            f"📂 Услуга: {review.get('service_type')}\n"
            f"⭐️ Оценка: {_stars(review.get('rating') or 0)}\n"
            f"📌 Статус: {review.get('status')}\n\n"
            f"💬 Текст:\n{review.get('text') or ''}"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=_moderation_markup(review_id))

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith("review_approve_")
        or call.data.startswith("review_reject_")
        or call.data.startswith("approve_review_")
        or call.data.startswith("reject_review_")
    )
    def handle_review_moderation(call):
        parts = call.data.split("_")
        if call.data.startswith(("review_approve_", "review_reject_")):
            action = parts[1]
            review_id = int(parts[2])
        else:
            action = parts[0]
            review_id = int(parts[2])

        try:
            ok = approve_review(review_id) if action == "approve" else delete_review(review_id)
        except Exception as exc:
            logger.error("Error moderating review %s: %s", review_id, exc)
            bot.answer_callback_query(call.id, "❌ Ошибка модерации", show_alert=True)
            return
        status_text = "✅ Отзыв одобрен" if action == "approve" else "❌ Отзыв отклонён"
        if not ok:
            bot.answer_callback_query(call.id, "❌ Отзыв не найден", show_alert=True)
            return
        bot.edit_message_text(f"{call.message.text}\n\n{status_text}", call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, status_text)
