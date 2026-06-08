"""Balance top-up UI and payment-provider handlers."""
from __future__ import annotations

from datetime import datetime
import re
import time

import requests
from telebot import types

from services import payments


TOPUP_AMOUNTS = (300, 500, 1000, 2000)


def _topup_text() -> str:
    return "💳 Пополнение баланса\n\nВыберите сумму:"


def _amount_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    for amount in TOPUP_AMOUNTS:
        markup.add(types.InlineKeyboardButton(f"{amount}₽", callback_data=f"topup_{amount}"))
    markup.add(types.InlineKeyboardButton("Другая сумма", callback_data="topup_custom"))
    markup.add(types.InlineKeyboardButton("◀️ Отмена", callback_data="back_to_profile"))
    return markup


def _payment_method_markup(amount: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("💳 YooKassa", callback_data=f"yookassa_pay_{amount}"),
        types.InlineKeyboardButton("🤖 Crypto Bot", callback_data=f"crypto_pay_{amount}"),
        types.InlineKeyboardButton("⭐ Telegram Stars", callback_data=f"stars_pay_{amount}"),
        types.InlineKeyboardButton("💎 TON", callback_data=f"ton_pay_{amount}"),
        types.InlineKeyboardButton("◀️ Назад", callback_data="topup_back"),
    )
    return markup


def _parse_amount(text: str) -> int | None:
    try:
        amount = int(re.sub(r"[^0-9]", "", text or ""))
        return amount if amount > 0 else None
    except Exception:
        return None


def _send_amount_menu(bot, chat_id: int, message_id: int | None = None) -> None:
    if message_id is None:
        bot.send_message(chat_id, _topup_text(), reply_markup=_amount_markup())
        return
    try:
        bot.edit_message_text(_topup_text(), chat_id, message_id, reply_markup=_amount_markup())
    except Exception:
        bot.send_message(chat_id, _topup_text(), reply_markup=_amount_markup())


def _send_payment_methods(bot, call, amount: int) -> None:
    text = f"💰 Пополнение баланса на {amount}₽\n\nВыберите способ оплаты:"
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=_payment_method_markup(amount))
    except Exception:
        bot.send_message(call.message.chat.id, text, reply_markup=_payment_method_markup(amount))


def _provider_unavailable(bot, call) -> None:
    bot.answer_callback_query(call.id, "❌ Способ оплаты временно недоступен", show_alert=True)


def _parse_provider_amount(call) -> int | None:
    try:
        amount = int(call.data.split("_")[2])
    except Exception:
        return None
    return amount if 50 <= amount <= 100000 else None


def _save_topup_order(ctx: dict, user_id: int, amount: int, payment_id: str) -> bool:
    conn = None
    cursor = None
    try:
        conn = ctx["get_pg_connection"]()
        if not conn:
            return False
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO orders (user_id, service_type, amount, status, payment_id, created_date) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (user_id, "topup", amount, "pending", payment_id, datetime.now()),
        )
        conn.commit()
        return True
    except Exception as exc:
        logger = ctx.get("logger")
        if logger:
            logger.error("DB error while creating topup order: %s", exc)
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            ctx["return_pg_connection"](conn)


def _change_user_balance(ctx: dict, user_id: int, delta: float) -> bool:
    return payments.change_user_balance(
        user_id,
        delta,
        ctx["get_pg_connection"],
        ctx["return_pg_connection"],
        ctx.get("logger"),
    )


def _cancel_pending_topup_orders(ctx: dict, user_id: int) -> int:
    return payments.cancel_pending_topup_orders(
        user_id,
        ctx["get_pg_connection"],
        ctx["return_pg_connection"],
        ctx.get("logger"),
    )


def _create_yookassa_payment(bot, call, ctx: dict) -> None:
    amount = _parse_provider_amount(call)
    if amount is None:
        bot.answer_callback_query(call.id, "❌ Неверная сумма для платежа", show_alert=True)
        return

    logger = ctx.get("logger")
    configuration = ctx.get("yookassa_configuration")
    payment_cls = ctx.get("yookassa_payment")
    if not ctx.get("yookassa_available") or configuration is None or payment_cls is None:
        if logger:
            logger.error("YooKassa module not available")
        bot.answer_callback_query(call.id, "❌ Модуль YooKassa недоступен", show_alert=True)
        return

    if not getattr(configuration, "account_id", None) or not getattr(configuration, "secret_key", None):
        if logger:
            logger.error("YooKassa configuration missing")
        bot.answer_callback_query(call.id, "❌ Не настроена конфигурация YooKassa", show_alert=True)
        return

    try:
        payment = payment_cls.create(
            {
                "amount": {"value": f"{amount:.2f}", "currency": "RUB"},
                "confirmation": {"type": "redirect", "return_url": "https://t.me/twaslabel_bot"},
                "capture": True,
                "description": f"Пополнение баланса пользователя {call.from_user.id}",
                "metadata": {"user_id": str(call.from_user.id), "service": "topup"},
            }
        )
        payment_url = payment.confirmation.confirmation_url
        payment_id = payment.id

        if not _save_topup_order(ctx, call.from_user.id, amount, payment_id):
            bot.answer_callback_query(call.id, "❌ Ошибка при создании платежа", show_alert=True)
            return

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("💳 Перейти к оплате", url=payment_url),
            types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_payment_{payment_id}"),
        )
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_topup"))
        bot.edit_message_text(
            f"💳 Пополнение на {amount}₽ через YooKassa\n\nНажмите для оплаты, затем проверьте статус.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
    except Exception as exc:
        if logger:
            logger.error("Failed to create YooKassa payment: %s", exc)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💳 Crypto Bot", callback_data=f"crypto_pay_{amount}"))
        markup.add(types.InlineKeyboardButton("⭐ Telegram Stars", callback_data=f"stars_pay_{amount}"))
        markup.add(types.InlineKeyboardButton("🔄 Попробовать снова", callback_data=f"yookassa_pay_{amount}"))
        bot.answer_callback_query(call.id, "❌ Ошибка при создании платежа в YooKassa", show_alert=True)
        bot.edit_message_text(
            "❌ Ошибка при создании платежа в YooKassa\n\nПопробуйте другие способы оплаты:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )


def _create_crypto_payment(bot, call, ctx: dict) -> None:
    amount = _parse_provider_amount(call)
    if amount is None:
        bot.answer_callback_query(call.id, "❌ Неверная сумма для платежа", show_alert=True)
        return

    token = ctx.get("crypto_bot_token")
    if not token:
        bot.answer_callback_query(call.id, "❌ Crypto Bot не настроен", show_alert=True)
        return

    logger = ctx.get("logger")
    try:
        response = requests.post(
            "https://pay.crypt.bot/api/createInvoice",
            json={
                "asset": "USDT",
                "amount": amount / 100,
                "description": f"Пополнение баланса пользователя {call.from_user.id}",
                "payload": f"topup_{call.from_user.id}_{amount}",
            },
            headers={"Crypto-Pay-API-Token": token, "Content-Type": "application/json"},
            timeout=20,
        )
        if response.status_code != 200:
            bot.answer_callback_query(call.id, "❌ Ошибка подключения к Crypto Bot", show_alert=True)
            return
        data = response.json()
        if not data.get("ok"):
            bot.answer_callback_query(call.id, "❌ Ошибка создания счета в Crypto Bot", show_alert=True)
            return

        invoice_id = str(data["result"]["invoice_id"])
        pay_url = data["result"]["pay_url"]
        if not _save_topup_order(ctx, call.from_user.id, amount, invoice_id):
            bot.answer_callback_query(call.id, "❌ Ошибка при создании платежа", show_alert=True)
            return

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("🤖 Перейти к оплате", url=pay_url),
            types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_crypto_{invoice_id}"),
        )
        markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_topup"))
        bot.edit_message_text(
            f"🤖 Пополнение на {amount}₽ через Crypto Bot\n\nНажмите для оплаты, затем проверьте статус.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup,
        )
    except Exception as exc:
        if logger:
            logger.error("Failed to create Crypto Bot payment: %s", exc)
        bot.answer_callback_query(call.id, "❌ Ошибка при создании платежа в Crypto Bot", show_alert=True)


def _create_stars_payment(bot, call, ctx: dict) -> None:
    amount = _parse_provider_amount(call)
    if amount is None:
        bot.answer_callback_query(call.id, "❌ Неверная сумма для платежа", show_alert=True)
        return

    payment_id = f"stars_{call.from_user.id}_{int(time.time())}"
    if not _save_topup_order(ctx, call.from_user.id, amount, payment_id):
        bot.answer_callback_query(call.id, "❌ Ошибка при создании платежа", show_alert=True)
        return

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("⭐ Оплатить Stars", callback_data=f"pay_stars_{payment_id}"),
        types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_stars_{payment_id}"),
    )
    markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_topup"))
    bot.edit_message_text(
        f"⭐ Пополнение на {amount}₽ через Telegram Stars\n\n"
        "Для оплаты нажмите кнопку 'Оплатить Stars' и следуйте инструкциям.",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
    )


def _create_ton_payment(bot, call, ctx: dict) -> None:
    amount = _parse_provider_amount(call)
    if amount is None:
        bot.answer_callback_query(call.id, "❌ Неверная сумма для платежа", show_alert=True)
        return

    payment_id = f"ton_{call.from_user.id}_{int(time.time())}"
    ton_wallet = ctx.get("ton_wallet") or "EQD4FPq-PRDieyQKkizFTRtSDyucUIqrj0v_zXJmqaHp6_0t"
    if not _save_topup_order(ctx, call.from_user.id, amount, payment_id):
        bot.answer_callback_query(call.id, "❌ Ошибка при создании платежа", show_alert=True)
        return

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("💎 Скопировать адрес TON", callback_data=f"copy_ton_{ton_wallet}"),
        types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_ton_{payment_id}"),
    )
    markup.add(types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_topup"))
    bot.edit_message_text(
        f"💎 Пополнение на {amount}₽ через TON\n\n"
        f"Отправьте {amount}₽ на адрес:\n"
        f"`{ton_wallet}`\n\n"
        "После оплаты нажмите 'Проверить оплату'",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode="Markdown",
    )


def _check_crypto_payment(bot, call, ctx: dict) -> None:
    invoice_id = call.data.split("_")[2]
    token = ctx.get("crypto_bot_token")
    if not token:
        bot.answer_callback_query(call.id, "❌ Crypto Bot не настроен", show_alert=True)
        return

    logger = ctx.get("logger")
    try:
        response = requests.post(
            "https://pay.crypt.bot/api/getInvoices",
            json={"invoice_ids": invoice_id},
            headers={"Crypto-Pay-API-Token": token, "Content-Type": "application/json"},
            timeout=20,
        )
        if response.status_code != 200:
            bot.answer_callback_query(call.id, "❌ Ошибка проверки статуса", show_alert=True)
            return

        data = response.json()
        if not data.get("ok") or not data["result"]["items"]:
            bot.answer_callback_query(call.id, "❌ Счет не найден", show_alert=True)
            return

        status = data["result"]["items"][0].get("status")
        if status != "paid":
            if status == "active":
                bot.answer_callback_query(call.id, "⏳ Платеж еще не поступил", show_alert=True)
            else:
                bot.answer_callback_query(call.id, f"❌ Статус платежа: {status}", show_alert=True)
            return

        conn = None
        cursor = None
        try:
            conn = ctx["get_pg_connection"]()
            if not conn:
                bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
                return
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, amount FROM orders WHERE payment_id = %s", (invoice_id,))
            order_info = cursor.fetchone()
            if not order_info:
                bot.answer_callback_query(call.id, "❌ Заказ не найден", show_alert=True)
                return
            user_id, amount = order_info
            cursor.execute("UPDATE orders SET status = %s WHERE payment_id = %s", ("completed", invoice_id))
            conn.commit()
            if not _change_user_balance(ctx, user_id, amount):
                bot.answer_callback_query(call.id, "❌ Ошибка зачисления баланса", show_alert=True)
                return
            bot.edit_message_text(
                f"✅ Платеж успешно обработан!\n\nВаш баланс пополнен на {amount}₽",
                call.message.chat.id,
                call.message.message_id,
            )
        finally:
            if cursor:
                cursor.close()
            if conn:
                ctx["return_pg_connection"](conn)
    except Exception as exc:
        if logger:
            logger.error("Error checking Crypto Bot payment: %s", exc)
        bot.answer_callback_query(call.id, "❌ Ошибка проверки платежа", show_alert=True)


def _open_stars_payment(bot, call) -> None:
    payment_id = call.data.split("_")[2]
    stars_url = f"https://t.me/StarsBot?start=pay_{payment_id}"
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("⭐ Открыть Stars", url=stars_url),
        types.InlineKeyboardButton("✅ Проверить оплату", callback_data=f"check_stars_{payment_id}"),
    )
    bot.edit_message_text(
        "⭐ Оплата через Telegram Stars\n\n"
        "Нажмите 'Открыть Stars' для перехода к оплате.\n"
        "После завершения оплаты нажмите 'Проверить оплату'.",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
    )


def _manual_check_message(bot, call, provider_label: str, payment_id: str) -> None:
    callback_prefix = "check_stars" if provider_label == "Stars" else "check_ton"
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🔄 Проверить снова", callback_data=f"{callback_prefix}_{payment_id}"),
        types.InlineKeyboardButton("❌ Отмена", callback_data="cancel_topup"),
    )
    bot.edit_message_text(
        f"{'⭐' if provider_label == 'Stars' else '💎'} Проверка оплаты {provider_label}\n\n"
        "Для проверки статуса оплаты обратитесь к администратору или попробуйте позже.\n"
        f"ID платежа: {payment_id}",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
    )


def _handle_provider_payment(bot, call, payment_handlers: dict, payment_context: dict, provider: str) -> None:
    handler = payment_handlers.get(provider)
    if handler is not None:
        handler(call)
        return
    if provider == "yookassa" and payment_context:
        _create_yookassa_payment(bot, call, payment_context)
        return
    if provider == "crypto" and payment_context:
        _create_crypto_payment(bot, call, payment_context)
        return
    if provider == "stars" and payment_context:
        _create_stars_payment(bot, call, payment_context)
        return
    if provider == "ton" and payment_context:
        _create_ton_payment(bot, call, payment_context)
        return
    _provider_unavailable(bot, call)


def register_topup_handlers(
    bot,
    payment_handlers: dict | None = None,
    payment_context: dict | None = None,
) -> None:
    payment_handlers = payment_handlers or {}
    payment_context = payment_context or {}

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "💳 Пополнить баланс")
    def handle_topup_request(message):
        bot.reply_to(message, _topup_text(), reply_markup=_amount_markup())

    @bot.callback_query_handler(
        func=lambda call: call.data.startswith("topup_")
        and not call.data.startswith("topup_pay_")
        and call.data not in ("topup_back", "topup_from_profile")
    )
    def handle_topup_callback(call):
        bot.answer_callback_query(call.id)
        if call.data == "topup_custom":
            bot.edit_message_text("Введите сумму пополнения (целое число рублей):", call.message.chat.id, call.message.message_id)
            bot.register_next_step_handler(call.message, process_custom_topup_amount)
            return
        amount = int(call.data.split("_")[1])
        _send_payment_methods(bot, call, amount)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("topup_pay_"))
    def handle_topup_pay(call):
        bot.answer_callback_query(call.id)
        amount = int(call.data.split("_")[2])
        _send_payment_methods(bot, call, amount)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("yookassa_pay_"))
    def handle_yookassa_payment(call):
        _handle_provider_payment(bot, call, payment_handlers, payment_context, "yookassa")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("crypto_pay_"))
    def handle_crypto_payment(call):
        _handle_provider_payment(bot, call, payment_handlers, payment_context, "crypto")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("stars_pay_"))
    def handle_stars_payment(call):
        _handle_provider_payment(bot, call, payment_handlers, payment_context, "stars")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("ton_pay_"))
    def handle_ton_payment(call):
        _handle_provider_payment(bot, call, payment_handlers, payment_context, "ton")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("check_crypto_"))
    def handle_crypto_payment_check(call):
        if not payment_context:
            _provider_unavailable(bot, call)
            return
        _check_crypto_payment(bot, call, payment_context)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("pay_stars_"))
    def handle_pay_stars(call):
        _open_stars_payment(bot, call)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("check_stars_"))
    def handle_check_stars(call):
        _manual_check_message(bot, call, "Stars", call.data.split("_")[2])

    @bot.callback_query_handler(func=lambda call: call.data.startswith("copy_ton_"))
    def handle_copy_ton_address(call):
        wallet_address = call.data.split("_", 2)[2]
        bot.answer_callback_query(call.id, f"💎 Адрес TON скопирован: {wallet_address}", show_alert=True)
        bot.edit_message_text(
            f"💎 Адрес TON скопирован!\n\n"
            f"Адрес: `{wallet_address}`\n\n"
            "📋 Скопируйте адрес вручную и отправьте нужную сумму.\n"
            "После оплаты нажмите 'Проверить оплату'.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="Markdown",
        )

    @bot.callback_query_handler(func=lambda call: call.data.startswith("check_ton_"))
    def handle_check_ton(call):
        _manual_check_message(bot, call, "TON", call.data.split("_")[2])

    @bot.callback_query_handler(func=lambda call: call.data == "cancel_topup")
    def handle_cancel_topup(call):
        cancelled_count = 0
        if payment_context:
            cancelled_count = _cancel_pending_topup_orders(payment_context, call.from_user.id)
            logger = payment_context.get("logger")
            if logger:
                logger.info("Cancelled %s pending topup orders for user %s", cancelled_count, call.from_user.id)
        try:
            bot.edit_message_text("❌ Пополнение баланса отменено", call.message.chat.id, call.message.message_id)
        except Exception:
            bot.send_message(call.message.chat.id, "❌ Пополнение баланса отменено")
        bot.send_message(call.message.chat.id, "Выберите действие:", reply_markup=_amount_markup())

    @bot.callback_query_handler(func=lambda call: call.data == "topup_back")
    def handle_topup_back(call):
        bot.answer_callback_query(call.id)
        _send_amount_menu(bot, call.message.chat.id, call.message.message_id)

    @bot.callback_query_handler(func=lambda call: call.data == "topup_from_profile")
    def handle_topup_from_profile(call):
        bot.answer_callback_query(call.id)
        _send_amount_menu(bot, call.message.chat.id, call.message.message_id)

    def process_custom_topup_amount(message):
        amount = _parse_amount(getattr(message, "text", ""))
        if amount is None:
            sent = bot.reply_to(message, "❌ Неверная сумма. Введите положительное число, например: 500")
            bot.register_next_step_handler(sent, process_custom_topup_amount)
            return

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Перейти к оплате", callback_data=f"topup_pay_{amount}"))
        bot.send_message(message.chat.id, f"К оплате: {amount}₽", reply_markup=markup)
