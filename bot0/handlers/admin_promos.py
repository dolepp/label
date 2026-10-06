"""Admin promo read-only/menu handlers."""
from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

from telebot import types

from core.config import ADMIN_IDS, PERMANENT_ADMINS
from db.repositories.promos import create_promo, delete_unused_promo, get_admin_promo_stats, list_unused_promos
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


def _promo_menu_markup(back_callback: str = "admin_finance"):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("➕ Создать промокод", callback_data="promo_create"),
        types.InlineKeyboardButton("📊 Статистика промокодов", callback_data="promo_stats"),
        types.InlineKeyboardButton("❌ Удалить промокоды", callback_data="promo_delete"),
        types.InlineKeyboardButton("◀️ Назад", callback_data=back_callback),
    )
    return markup


def _money(value) -> str:
    amount = Decimal(value or 0)
    return f"{amount}₽"


def _promo_stats_text(stats: dict) -> str:
    return (
        "📊 Статистика промокодов\n\n"
        f"Всего промокодов: {stats['total']}\n"
        f"Активных: {stats['active']}\n"
        f"Истекших: {stats['expired']}\n"
        f"С лимитом использований: {stats['limited_usage']}\n"
        f"Общая сумма всех: {_money(stats['total_amount'])}\n"
        f"Сумма использованных: {_money(stats['used_amount'])}"
    )


def _promo_delete_caption(promo: dict) -> str:
    code = promo["code"]
    discount = Decimal(promo.get("discount") or 0)
    if discount:
        return f"❌ {code} ({discount:.0f}%)"
    return f"❌ {code} ({_money(promo.get('amount'))})"


def _require_admin(bot, call) -> bool:
    if _is_admin(call.from_user.id):
        return True
    bot.answer_callback_query(call.id, "У вас нет доступа к этой функции.", show_alert=True)
    return False


def _create_menu_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💰 Промокод на пополнение баланса", callback_data="promo_create_balance"),
        types.InlineKeyboardButton("🎟 Промокод на скидку", callback_data="promo_create_discount"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="finance_promo"),
    )
    return markup


def _balance_type_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔢 С ограничением по использованию", callback_data="promo_create_limited"),
        types.InlineKeyboardButton("⏰ С ограничением по времени", callback_data="promo_create_timed"),
        types.InlineKeyboardButton("♾️ Без ограничений", callback_data="promo_create_unlimited"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="promo_create"),
    )
    return markup


def _discount_type_markup():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🔢 С ограничением по использованию", callback_data="promo_create_discount_limited"),
        types.InlineKeyboardButton("⏰ С ограничением по времени", callback_data="promo_create_discount_timed"),
        types.InlineKeyboardButton("♾️ Без ограничений", callback_data="promo_create_discount_unlimited"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="promo_create"),
    )
    return markup


def _parse_positive_decimal(value: str, title: str) -> Decimal:
    try:
        parsed = Decimal(value.replace(",", "."))
    except Exception as exc:
        raise ValueError(f"{title} должен быть числом") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{title} должен быть больше 0")
    return parsed


def _parse_date(raw: str) -> datetime:
    try:
        parsed = datetime.strptime(raw, "%d.%m.%Y")
    except ValueError as exc:
        raise ValueError("Дата в формате ДД.ММ.ГГГГ") from exc
    return parsed.replace(hour=23, minute=59, second=59)


def _success_text(promo: dict) -> str:
    if Decimal(promo.get("discount") or 0) > 0:
        text = f"✅ Промокод на скидку создан!\n\nКод: {promo['code']}\nСкидка: {Decimal(promo['discount']):.0f}%"
    else:
        text = f"✅ Промокод создан!\n\nКод: {promo['code']}\nСумма: {Decimal(promo['amount']):.2f}₽"
    if promo.get("max_uses"):
        text += f"\nМакс. активаций: {promo['max_uses']}"
    if promo.get("expires_at"):
        text += f"\nДействует до: {promo['expires_at'].strftime('%d.%m.%Y')}"
    return text


def _handle_create_error(bot, message, exc: Exception) -> None:
    if "duplicate" in str(exc).lower() or "unique" in str(exc).lower():
        bot.reply_to(message, "❌ Промокод с таким кодом уже существует")
        return
    bot.reply_to(message, f"❌ Ошибка: {exc}")


def register_admin_promo_handlers(bot) -> None:
    @bot.callback_query_handler(func=lambda call: call.data == "finance_promo")
    def handle_finance_promo(call):
        if not _require_admin(bot, call):
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🎟 Управление промокодами",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_promo_menu_markup("admin_finance"),
        )

    @bot.callback_query_handler(func=lambda call: call.data == "promo_create")
    def handle_promo_create(call):
        if not _require_admin(bot, call):
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🎟 Создание промокода\n\nВыберите тип промокода:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_create_menu_markup(),
        )

    @bot.callback_query_handler(func=lambda call: call.data == "promo_create_balance")
    def handle_promo_create_balance(call):
        if not _require_admin(bot, call):
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "💰 Промокод на пополнение баланса\n\nВыберите тип ограничения:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_balance_type_markup(),
        )

    @bot.callback_query_handler(func=lambda call: call.data == "promo_create_discount")
    def handle_promo_create_discount(call):
        if not _require_admin(bot, call):
            return
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "🎟 Промокод на скидку\n\nВыберите тип ограничения:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=_discount_type_markup(),
        )

    @bot.callback_query_handler(func=lambda call: call.data == "promo_create_limited")
    def handle_promo_create_limited(call):
        if not _require_admin(bot, call):
            return
        bot.edit_message_text(
            "🔢 Создание промокода с ограничением по использованию\n\n"
            "Введите данные в формате:\nКОД СУММА КОЛИЧЕСТВО_ИСПОЛЬЗОВАНИЙ\n\n"
            "Например: WELCOME2024 1000 50",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.register_next_step_handler(call.message, process_balance_limited)

    @bot.callback_query_handler(func=lambda call: call.data == "promo_create_timed")
    def handle_promo_create_timed(call):
        if not _require_admin(bot, call):
            return
        bot.edit_message_text(
            "⏰ Создание промокода с ограничением по времени\n\n"
            "Введите данные в формате:\nКОД СУММА ДАТА_ОКОНЧАНИЯ\n\n"
            "Например: SUMMER2024 500 31.12.2026\nФормат даты: ДД.ММ.ГГГГ",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.register_next_step_handler(call.message, process_balance_timed)

    @bot.callback_query_handler(func=lambda call: call.data == "promo_create_unlimited")
    def handle_promo_create_unlimited(call):
        if not _require_admin(bot, call):
            return
        bot.edit_message_text(
            "♾️ Создание промокода без ограничений\n\nВведите данные в формате:\nКОД СУММА\n\nНапример: VIP2024 2000",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.register_next_step_handler(call.message, process_balance_unlimited)

    @bot.callback_query_handler(func=lambda call: call.data == "promo_create_discount_limited")
    def handle_promo_create_discount_limited(call):
        if not _require_admin(bot, call):
            return
        bot.edit_message_text(
            "🔢 Промокод на скидку с ограничением по использованию\n\n"
            "Введите в формате: КОД ПРОЦЕНТ КОЛИЧЕСТВО_АКТИВАЦИЙ\n\nНапример: SALE20 20 100",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.register_next_step_handler(call.message, process_discount_limited)

    @bot.callback_query_handler(func=lambda call: call.data == "promo_create_discount_timed")
    def handle_promo_create_discount_timed(call):
        if not _require_admin(bot, call):
            return
        bot.edit_message_text(
            "⏰ Промокод на скидку с ограничением по времени\n\n"
            "Введите в формате: КОД ПРОЦЕНТ ДАТА_ОКОНЧАНИЯ\n\n"
            "Например: SALE20 20 31.12.2026\nФормат даты: ДД.ММ.ГГГГ",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.register_next_step_handler(call.message, process_discount_timed)

    @bot.callback_query_handler(func=lambda call: call.data == "promo_create_discount_unlimited")
    def handle_promo_create_discount_unlimited(call):
        if not _require_admin(bot, call):
            return
        bot.edit_message_text(
            "♾️ Промокод на скидку без ограничений\n\nВведите в формате: КОД ПРОЦЕНТ\n\nНапример: SALE20 20",
            call.message.chat.id,
            call.message.message_id,
        )
        bot.register_next_step_handler(call.message, process_discount_unlimited)

    def process_balance_limited(message):
        if not _is_admin(message.from_user.id):
            bot.reply_to(message, "У вас нет доступа к этой функции.")
            return
        try:
            code, raw_amount, raw_limit = (message.text or "").strip().split()
            amount = _parse_positive_decimal(raw_amount, "Сумма")
            max_uses = int(raw_limit)
            if max_uses <= 0:
                raise ValueError("Количество использований должно быть больше 0")
            promo = create_promo(code=code, amount=amount, created_by=message.from_user.id, max_uses=max_uses)
            bot.reply_to(message, _success_text(promo))
        except ValueError as exc:
            bot.reply_to(message, f"❌ {exc}")
        except Exception as exc:
            _handle_create_error(bot, message, exc)

    def process_balance_timed(message):
        if not _is_admin(message.from_user.id):
            bot.reply_to(message, "У вас нет доступа к этой функции.")
            return
        try:
            code, raw_amount, raw_date = (message.text or "").strip().split()
            amount = _parse_positive_decimal(raw_amount, "Сумма")
            expires_at = _parse_date(raw_date)
            if expires_at <= datetime.now():
                raise ValueError("Дата окончания должна быть в будущем")
            promo = create_promo(code=code, amount=amount, created_by=message.from_user.id, expires_at=expires_at)
            bot.reply_to(message, _success_text(promo))
        except ValueError as exc:
            bot.reply_to(message, f"❌ {exc}")
        except Exception as exc:
            _handle_create_error(bot, message, exc)

    def process_balance_unlimited(message):
        if not _is_admin(message.from_user.id):
            bot.reply_to(message, "У вас нет доступа к этой функции.")
            return
        try:
            code, raw_amount = (message.text or "").strip().split()
            amount = _parse_positive_decimal(raw_amount, "Сумма")
            promo = create_promo(code=code, amount=amount, created_by=message.from_user.id)
            bot.reply_to(message, _success_text(promo))
        except ValueError as exc:
            bot.reply_to(message, f"❌ {exc}")
        except Exception as exc:
            _handle_create_error(bot, message, exc)

    def process_discount_limited(message):
        _process_discount(message, mode="limited")

    def process_discount_timed(message):
        _process_discount(message, mode="timed")

    def process_discount_unlimited(message):
        _process_discount(message, mode="unlimited")

    def _process_discount(message, mode: str):
        if not _is_admin(message.from_user.id):
            bot.reply_to(message, "У вас нет доступа к этой функции.")
            return
        try:
            parts = (message.text or "").strip().split()
            if len(parts) < 2:
                raise ValueError("Формат: КОД ПРОЦЕНТ [лимит или дата]")
            code = parts[0]
            discount = _parse_positive_decimal(parts[1], "Процент скидки")
            if discount >= 100:
                raise ValueError("Процент скидки: от 1 до 99")
            max_uses = None
            expires_at = None
            if mode == "limited":
                if len(parts) < 3:
                    raise ValueError("Для лимита введите: КОД ПРОЦЕНТ КОЛИЧЕСТВО")
                max_uses = int(parts[2])
                if max_uses <= 0:
                    raise ValueError("Количество активаций должно быть > 0")
            elif mode == "timed":
                if len(parts) < 3:
                    raise ValueError("Для лимита по времени введите: КОД ПРОЦЕНТ ДАТА")
                expires_at = _parse_date(parts[2])
            promo = create_promo(
                code=code,
                amount=0,
                discount=discount,
                created_by=message.from_user.id,
                max_uses=max_uses,
                expires_at=expires_at,
            )
            bot.reply_to(message, _success_text(promo))
        except ValueError as exc:
            bot.reply_to(message, f"❌ {exc}")
        except Exception as exc:
            _handle_create_error(bot, message, exc)

    @bot.callback_query_handler(func=lambda call: call.data == "promo_stats")
    def handle_promo_stats(call):
        if not _require_admin(bot, call):
            return
        stats = get_admin_promo_stats()
        if not stats:
            bot.answer_callback_query(call.id, "❌ Ошибка получения статистики", show_alert=True)
            return
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="finance_promo"))
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            _promo_stats_text(stats),
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )

    @bot.callback_query_handler(func=lambda call: call.data == "promo_delete")
    def handle_promo_delete(call):
        if not _require_admin(bot, call):
            return

        try:
            unused_codes = list_unused_promos()
        except Exception as exc:
            logger.error("PostgreSQL error in promo delete: %s", exc)
            bot.answer_callback_query(call.id, "❌ Ошибка получения списка промокодов", show_alert=True)
            return

        markup = types.InlineKeyboardMarkup(row_width=1)
        if not unused_codes:
            markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="finance_promo"))
            bot.edit_message_text(
                "❌ Нет неиспользованных промокодов для удаления",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
            )
            return

        for promo in unused_codes:
            markup.add(
                types.InlineKeyboardButton(
                    _promo_delete_caption(promo),
                    callback_data=f"delete_promo_{promo['code']}",
                )
            )
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="finance_promo"))
        bot.answer_callback_query(call.id)
        bot.edit_message_text(
            "❌ Выберите промокод для удаления:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("delete_promo_"))
    def handle_delete_promo(call):
        if not _require_admin(bot, call):
            return

        code = call.data.split("_", 2)[2]
        try:
            deleted = delete_unused_promo(code)
        except Exception as exc:
            logger.error("PostgreSQL error in delete promo: %s", exc)
            bot.answer_callback_query(call.id, "❌ Ошибка удаления промокода", show_alert=True)
            return

        if not deleted:
            bot.answer_callback_query(call.id, "❌ Промокод не найден или уже использован", show_alert=True)
            return

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("◀️ Назад", callback_data="finance_promo"))
        bot.answer_callback_query(call.id, f"✅ Промокод {code} удален")
        bot.edit_message_text(
            f"✅ Промокод {code} успешно удален",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
