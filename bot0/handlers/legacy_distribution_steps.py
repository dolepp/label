"""Legacy Telegram distribution step-chain handlers.

This module owns the old reply-keyboard distribution flow that used to live in
label.py. Runtime dependencies are injected by the launcher/registration layer
so this code does not import the monolith.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Callable

from telebot import types

from db.repositories.drafts import save_user_draft
from services.notifications import notify_admins_about_new_release as _notify_admins_about_new_release
from utils.security import validate_file_upload

logger = logging.getLogger(__name__)

bot = None
get_pg_connection: Callable[..., Any] | None = None
return_pg_connection: Callable[..., Any] | None = None
create_main_menu: Callable[..., Any] | None = None
is_admin: Callable[[int], bool] | None = None
BOT_TOKEN = ""


def configure_legacy_distribution_steps(**context: Any) -> None:
    """Inject bot and infrastructure dependencies without importing label.py."""
    globals().update({key: value for key, value in context.items() if value is not None})


def _require(name: str) -> Any:
    value = globals().get(name)
    if value is None:
        raise RuntimeError(f"legacy distribution dependency is not configured: {name}")
    return value


def is_cancel_message(message):
    """Проверка, что сообщение — отмена (кнопка «❌ Отмена», /cancel или «отмена»)."""
    if not message or not getattr(message, "text", None) or not message.text:
        return False
    t = (message.text or "").strip().lower()
    return t in ("/cancel", "отмена", "❌ отмена")


def is_save_draft_message(message):
    """Проверка, что сообщение — сохранение черновика."""
    if not message or not getattr(message, "text", None) or not message.text:
        return False
    t = (message.text or "").strip().lower()
    return t in ("💾 сохранить черновик", "сохранить черновик", "черновик")


def debug_user_data(user_id, step_name="unknown"):
    """Log compact user-data diagnostics for distribution flow."""
    try:
        data = getattr(bot, "user_data", {}).get(user_id, {}) if bot is not None else {}
        logger.info("Distribution user_data[%s] at %s: keys=%s", user_id, step_name, list(data.keys()))
    except Exception as exc:
        logger.debug("Could not log distribution user_data: %s", exc)


def notify_admins_about_new_release(user_id, release_id):
    _notify_admins_about_new_release(
        _require("bot"),
        user_id,
        release_id,
        _require("get_pg_connection"),
        _require("return_pg_connection"),
        logger,
    )
def save_draft_at_any_step(message):
    """Сохранить текущие данные раздачи как черновик на любом этапе."""
    user_id = message.from_user.id
    user_data = bot.user_data.get(user_id, {})
    if not user_data:
        bot.send_message(message.chat.id, "❌ Нет данных для сохранения.", reply_markup=create_main_menu())
        return
    try:
        draft_id = user_data.get("draft_id")
        saved_id = save_user_draft(
            user_id,
            "distribution_legacy",
            user_data,
            int(user_data.get("current_step") or 0),
            draft_id=draft_id,
        )
        if not saved_id:
            raise RuntimeError("draft was not saved")
        bot.clear_step_handler_by_chat_id(message.chat.id)
        bot.user_data.pop(user_id, None)
        bot.send_message(
            message.chat.id,
            "💾 Черновик сохранён!\n\nВы можете продолжить заполнение позже из раздела «Черновики» в профиле.",
            reply_markup=create_main_menu(),
        )
        logger.info(f"Draft saved for user {user_id} at any step")
    except Exception as e:
        logger.error(f"Error saving draft at any step for user {user_id}: {e}")
        bot.send_message(message.chat.id, "❌ Ошибка сохранения черновика. Попробуйте позже.")

def show_distribution_agreement(message):
    """Show distribution agreement"""
    agreement_text = (
        "🎵 Дистрибуция музыки\n\n"
        "Перед тем, как перейдем к отгрузке, необходимо согласиться с нижеследующим:\n\n"
        "- Мною выкуплен бит и у меня есть договор с артистом (если бит куплен, но нет договора, дальше будет пример договора, по которому нужно будет заключить соглашение на бит). Без договора релиз отгрузить не получится.\n"
        "- Я понимаю, что получение промо не гарантируется и является сугубо личным решением редакторов площадок, команда лейбла не может влиять на получение промо.\n"
        "- Я осознаю, что для получения промо релиз должен отгружаться за 2 недели до выхода.\n\n"
        "Вы согласны с этими условиями?"
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Согласен", callback_data="distribution_agree"),
        types.InlineKeyboardButton("❌ Не согласен", callback_data="distribution_disagree")
    )

    if hasattr(message, 'chat'):
        bot.send_message(message.chat.id, agreement_text, reply_markup=markup)
    else:
        bot.edit_message_text(
            agreement_text,
            message.chat.id,
            message.message_id,
            reply_markup=markup
        )

DISTRIBUTION_PRICES = {"Single": 1299, "Maxi Single": 1799, "EP": 2399, "ALBUM": 2899}


def _distribution_base_price(user_data: dict) -> int:
    return DISTRIBUTION_PRICES.get(user_data.get('release_type') or "Single", DISTRIBUTION_PRICES["Single"])


def _discounted_amount(base_amount: int, discount_pct: float) -> int:
    return max(1, int(base_amount * (1 - discount_pct / 100)))


def _user_is_artist(cursor, user_id: int) -> bool:
    cursor.execute('SELECT COALESCE(artist, 0) FROM label WHERE telegram_id = %s', (user_id,))
    row = cursor.fetchone()
    return bool(row and row[0])


def _owned_discount_promo(cursor, user_id: int, promo_id: int):
    """Скидочный промокод, который пользователь действительно активировал."""
    cursor.execute("""
        SELECT pc.code, COALESCE(pc.discount, 0)
        FROM user_discount_promos udp
        JOIN promo_codes pc ON pc.id = udp.promo_code_id AND pc.is_active = TRUE
        WHERE udp.user_id = %s AND pc.id = %s
        AND (pc.expires_at IS NULL OR pc.expires_at > CURRENT_TIMESTAMP)
    """, (user_id, promo_id))
    return cursor.fetchone()


def handle_distribution_pay(call):
    """Списать оплату дистрибуции. Сумма из кнопки только сверяется: её может подделать клиент."""
    try:
        claimed_amount = int(call.data.split("_")[2])
    except Exception:
        bot.answer_callback_query(call.id, "❌ Неверная сумма", show_alert=True)
        return

    user_id = call.from_user.id
    user_data = bot.user_data.get(user_id, {})
    if not user_data.get('release_type'):
        bot.answer_callback_query(call.id, "❌ Данные релиза не найдены. Заполните форму заново.", show_alert=True)
        return

    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к базе данных", show_alert=True)
        return

    cursor = None
    try:
        cursor = conn.cursor()
        if _user_is_artist(cursor, user_id):
            bot.answer_callback_query(call.id)
            save_release_data_for_user(user_id, call.message.chat.id)
            return

        base_amount = _distribution_base_price(user_data)
        amount = base_amount
        promo_id = user_data.get('distribution_promo_id')
        if promo_id and claimed_amount != base_amount:
            promo = _owned_discount_promo(cursor, user_id, promo_id)
            if promo:
                amount = _discounted_amount(base_amount, float(promo[1]))
        if claimed_amount != amount:
            user_data.pop('distribution_promo_id', None)
            user_data.pop('distribution_discount_pct', None)
            bot.answer_callback_query(call.id, f"❌ Сумма к оплате изменилась: {base_amount}₽. Нажмите «Оплатить» ещё раз.", show_alert=True)
            return
        if amount == base_amount:
            promo_id = None
            user_data.pop('distribution_promo_id', None)
            user_data.pop('distribution_discount_pct', None)

        cursor.execute(
            'UPDATE label SET balance = balance - %s WHERE telegram_id = %s AND COALESCE(balance, 0) >= %s RETURNING balance',
            (amount, user_id, amount),
        )
        charged = cursor.fetchone()
        conn.commit()
        cursor.execute('SELECT COALESCE(balance, 0) FROM label WHERE telegram_id = %s', (user_id,))
        row = cursor.fetchone()
        current_balance = float(row[0]) if row else 0.0

        if charged:
            user_data.pop('distribution_promo_id', None)
            user_data.pop('distribution_discount_pct', None)
            if promo_id:
                try:
                    cursor.execute('DELETE FROM user_discount_promos WHERE user_id = %s AND promo_code_id = %s', (user_id, promo_id))
                    cursor.execute(
                        'INSERT INTO promo_code_usage (user_id, promo_code_id, promo_code, amount_added) SELECT %s, %s, code, 0 FROM promo_codes WHERE id = %s',
                        (user_id, promo_id, promo_id)
                    )
                    conn.commit()
                except Exception as e:
                    logger.warning(f"Could not record discount promo usage: {e}")

            try:
                bot.edit_message_text(
                    f"✅ Списано {amount}₽ с баланса. Отправляем релиз на модерацию...",
                    call.message.chat.id,
                    call.message.message_id
                )
            except Exception:
                bot.send_message(call.message.chat.id, f"✅ Списано {amount}₽ с баланса. Отправляем релиз...")

            # Сохранить релиз для пользователя
            save_release_data_for_user(user_id, call.message.chat.id)
        else:
            needed = max(50, int(-(-(amount - current_balance) // 1)))
            markup = types.InlineKeyboardMarkup()
            # Сохраняем ожидаемую операцию, чтобы после пополнения продолжить автоматически и не терять прогресс
            bot.user_data.setdefault(user_id, {})['pending_operation'] = {
                'type': 'distribution',
                'amount': amount,
                'needed': needed,
                'resume': True
            }
            markup.add(
                types.InlineKeyboardButton(f"Пополнить на {needed}₽", callback_data=f"topup_pay_{needed}"),
                types.InlineKeyboardButton("Повторить оплату", callback_data=f"distribution_pay_{amount}")
            )
            bot.edit_message_text(
                f"❌ Недостаточно средств. Требуется {amount}₽, на балансе {current_balance:,.2f}₽.\n\nПополните баланс и попробуйте снова.",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
    except Exception as e:
        logger.error(f"Error in handle_distribution_pay: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка обработки оплаты", show_alert=True)
    finally:
        if cursor:
            cursor.close()
        return_pg_connection(conn)

def save_release_data_for_user(user_id: int, chat_id: int) -> None:
    """Save release using data from bot.user_data for specified user and notify."""
    user_data = bot.user_data.get(user_id, {})
    release_type = user_data.get('release_type', '')

    # Отладочная информация
    logger.info(f"Saving release for user {user_id}, release_type: {release_type}")
    logger.info(f"User data cover_file_id: {user_data.get('cover_file_id')}")
    logger.info(f"Full user_data keys: {list(user_data.keys())}")
    debug_user_data(user_id, "before_release_save")

    conn = get_pg_connection()
    if not conn:
        bot.send_message(chat_id, "❌ Ошибка подключения к БД")
        return

    try:
        cursor = conn.cursor()

        if release_type == "ALBUM" or release_type == "EP" or release_type == "Maxi Single":
            # Сохранение записи альбома/мульти-трекового релиза как альбома
            # Используем контракт первого трека для записи альбома
            first_track_contract = (user_data.get('tracks') or [{}])[0].get('contract_file_id', 'N/A')
            cursor.execute('''
                INSERT INTO releases (
                    user_id, release_type, artist_name, release_name,
                    genre, cover_file_id, release_date, performer_name,
                    music_author, contract_file_id, videoshot_url, explicit_content,
                    lyrics_file_id, preview_start, yandex_soon, create_links,
                    tiktok_commercial, tiktok_full_version, status, is_album
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                user_id,
                "ALBUM",
                user_data.get('album_artist') or user_data.get('artist_name'),
                user_data.get('album_name') or user_data.get('release_name'),
                (user_data.get('tracks') or [{}])[0].get('genre') or 'N/A',
                user_data.get('cover_file_id'),
                user_data.get('release_date'),
                user_data.get('performer_name'),
                user_data.get('music_author'),
                first_track_contract,
                user_data.get('videoshot_url'),
                user_data.get('explicit_content', False),
                user_data.get('lyrics_file_id'),
                user_data.get('preview_start'),
                user_data.get('yandex_soon', False),
                user_data.get('create_links', False),
                user_data.get('tiktok_commercial', False),
                user_data.get('tiktok_full_version', False),
                'pending',
                True
            ))
            album_id = cursor.fetchone()[0]

            # Сохранение треков
            for track in user_data.get('tracks', []):
                cursor.execute('''
                    INSERT INTO releases (
                        user_id, release_type, artist_name, release_name, producer, genre,
                        audio_file_id, release_date, performer_name, music_author,
                        contract_file_id, explicit_content, status, album_id, is_track, track_number,
                        lyrics_file_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    user_id,
                    "TRACK",
                    user_data.get('album_artist') or user_data.get('artist_name'),
                    track.get('track_name'),
                    track.get('producer'),
                    track.get('genre') or 'N/A',
                    track.get('audio_file_id'),
                    user_data.get('release_date'),
                    user_data.get('performer_name'),
                    user_data.get('music_author'),
                    track.get('contract_file_id'),
                    user_data.get('explicit_content', False),
                    'pending',
                    album_id,
                    True,
                    track.get('track_number'),
                    track.get('lyrics_file_id')
                ))

            release_name = user_data.get('album_name') or user_data.get('release_name') or 'Релиз'
            conn.commit()
            bot.send_message(chat_id, f"✅ Релиз «{release_name}» успешно отправлен на модерацию!",
                             reply_markup=create_main_menu())
            notify_admins_about_new_release(user_id, album_id)
        else:
            # Сохранение сингла
            cursor.execute('''
                INSERT INTO releases (
                    user_id, release_type, artist_name, release_name, producer, genre,
                    cover_file_id, audio_file_id, release_date, performer_name,
                    music_author, contract_file_id, videoshot_url, explicit_content,
                    lyrics_file_id, preview_start, yandex_soon, create_links,
                    tiktok_commercial, tiktok_full_version, status, is_album
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                user_id,
                user_data.get('release_type'),
                user_data.get('artist_name'),
                user_data.get('release_name'),
                user_data.get('producer'),
                user_data.get('genre') or 'N/A',
                user_data.get('cover_file_id'),
                user_data.get('audio_file_id'),
                user_data.get('release_date'),
                user_data.get('performer_name'),
                user_data.get('music_author'),
                user_data.get('contract_file_id'),
                user_data.get('videoshot_url'),
                user_data.get('explicit_content', False),
                user_data.get('lyrics_file_id'),
                user_data.get('preview_start'),
                user_data.get('yandex_soon', False),
                user_data.get('create_links', False),
                user_data.get('tiktok_commercial', False),
                user_data.get('tiktok_full_version', False),
                'pending',
                False
            ))
            release_id = cursor.fetchone()[0]
            release_name = user_data.get('release_name') or 'Релиз'
            conn.commit()
            bot.send_message(chat_id, f"✅ Релиз «{release_name}» успешно отправлен на модерацию!",
                             reply_markup=create_main_menu())
            notify_admins_about_new_release(user_id, release_id)
    except Exception as e:
        logger.exception("Ошибка сохранения релиза после оплаты")
        bot.send_message(chat_id, f"❌ Критическая ошибка: {str(e)}", reply_markup=create_main_menu())
    finally:
        # Не очищаем всю сессию пользователя, чтобы не терять прогресс при сценариях с пополнением
        if conn:
            cursor.close()
            return_pg_connection(conn)

def ask_release_type(message):
    """Запрос типа релиза с кнопкой отмены"""
    markup = create_options_keyboard(["Single", "Maxi Single", "EP", "ALBUM"])
    msg = bot.send_message(
        message.chat.id,
        "2) Тип релиза:\n\n"
        "📀 Выберите тип вашего музыкального релиза:\n\n"
        "🎵 Single - одна композиция (1299₽)\n"
        "🎶 Maxi Single - 1-3 композиции (1799₽)\n"
        "💿 EP - мини-альбом 2-5 треков (2399₽)\n"
        "💽 ALBUM - полноценный альбом 6+ треков (2899₽)",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, process_release_type)

def process_release_type(message):
    """Обработка типа релиза с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    release_type = message.text
    user_id = message.from_user.id

    # Инициализация данных пользователя
    if not hasattr(bot, 'user_data'):
        bot.user_data = {}
    bot.user_data[user_id] = {'release_type': release_type}

    # EP и Maxi Single ведём по трековому сценарию (как альбом)
    if release_type == "ALBUM":
        ask_track_count(message)
    elif release_type == "EP":
        # Запросим количество треков 2..5
        ask_track_count(message)
    elif release_type == "Maxi Single":
        # Жёстко 2 трека
        bot.user_data[user_id]['track_count'] = 2
        bot.user_data[user_id]['current_track'] = 1
        bot.user_data[user_id]['tracks'] = []
        ask_album_info(message)
    else:
        # Single
        ask_artist_name(message)

def ask_track_count(message):
    """Запрос количества треков с кнопкой отмены"""
    msg = bot.send_message(
        message.chat.id,
        "3) Количество треков в релизе:\n\n"
        "🔢 Укажите количество треков в вашем релизе:\n\n"
        "💿 EP: 2-5 треков (2399₽)\n"
        "💽 ALBUM: 6+ треков (2899₽)\n"
        "🎶 Maxi Single: 1-3 трека (1799₽)\n\n"
        "Введите количество треков:",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(msg, process_track_count)

def process_track_count(message):
    """Обработка количества треков с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    try:
        user_id = message.from_user.id
        track_count = int(message.text)
        release_type = bot.user_data[user_id].get('release_type')

        # Валидация по типу
        if release_type == "ALBUM":
            if track_count < 6 or track_count > 50:
                raise ValueError("Для альбома допустимо от 6 треков")
        elif release_type == "EP":
            if track_count < 2 or track_count > 5:
                raise ValueError("Для EP допустимо от 2 до 5 треков")
        elif release_type == "Maxi Single":
            if track_count < 1 or track_count > 3:
                raise ValueError("Для Maxi Single допустимо от 1 до 3 треков")
        else:
            if track_count < 1 or track_count > 1:
                raise ValueError("Для Single допустимо только 1 трек")

        bot.user_data[user_id]['track_count'] = track_count
        bot.user_data[user_id]['current_track'] = 1
        bot.user_data[user_id]['tracks'] = []

        ask_album_info(message)

    except (ValueError, TypeError) as e:
        msg = bot.send_message(
            message.chat.id,
            f"❌ {str(e) if str(e) else 'Пожалуйста, введите корректное число треков'}",
            reply_markup=create_cancel_keyboard()
        )
        bot.register_next_step_handler(msg, process_track_count)

def ask_album_info(message):
    """Запрос информации об альбоме с кнопкой отмены"""
    user_id = message.from_user.id
    current_track = bot.user_data[user_id]['current_track']

    if current_track == 1:
        bot.send_message(
            message.chat.id,
            "4) Название альбома:\n\n"
            "📝 Введите название вашего альбома/EP/Maxi Single:\n\n"
            "💡 Примеры:\n"
            "• \"Мой Первый Альбом\"\n"
            "• \"Летние Воспоминания EP\"\n"
            "• \"Best Tracks Collection\"\n\n"
            "Название должно быть уникальным и запоминающимся:",
            reply_markup=create_cancel_keyboard()
        )
        bot.register_next_step_handler(message, process_album_name)
    else:
        ask_track_info(message)

def process_album_name(message):
    """Обработка названия альбома с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    user_id = message.from_user.id
    bot.user_data[user_id]['album_name'] = message.text

    bot.send_message(
        message.chat.id,
        "5) Исполнитель(-и) альбома:\n\n"
        "🎤 Укажите основного исполнителя или группу:\n\n"
        "💡 Примеры:\n"
        "• \"Иван Иванов\"\n"
        "• \"The Best Band\"\n"
        "• \"MC Rapper feat. Singer\"\n\n"
        "📝 Если несколько исполнителей, перечислите через запятую:",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, process_album_artist)

def process_album_artist(message):
    """Обработка исполнителя альбома с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    user_id = message.from_user.id
    bot.user_data[user_id]['album_artist'] = message.text

    ask_track_info(message)

def ask_track_info(message):
    """Запрос информации о треке с кнопкой отмены"""
    user_id = message.from_user.id
    current_track = bot.user_data[user_id]['current_track']
    track_count = bot.user_data[user_id]['track_count']

    bot.send_message(
        message.chat.id,
        f"ТРЕК {current_track}/{track_count}\n\n"
        "6) Название трека:\n\n"
        "🎵 Введите название этого трека:\n\n"
        "💡 Примеры:\n"
        "• \"Моя Песня\"\n"
        "• \"Summer Vibes\"\n"
        "• \"Love Story (Remix)\"\n\n"
        "📝 Название должно точно соответствовать аудиофайлу:",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, process_track_name)

def process_track_name(message):
    """Обработка названия трека с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    user_id = message.from_user.id
    current_track = bot.user_data[user_id]['current_track']

    # Инициализация данных трека
    track_data = {
        'track_name': message.text,
        'track_number': current_track
    }
    bot.user_data[user_id]['tracks'].append(track_data)

    bot.send_message(
        message.chat.id,
        f"7) Продюсер трека (prod. by):\n\n"
        "🎛️ Укажите продюсера/битмейкера этого трека:\n\n"
        "💡 Примеры:\n"
        "• \"BeatMaker\"\n"
        "• \"ProducerName\"\n"
        "• \"DJ Producer\"\n\n"
        "📝 Будет отображаться как: [prod. by ВашПродюсер]",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, process_track_producer)

def process_track_producer(message):
    """Обработка продюсера трека с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    user_id = message.from_user.id
    current_track_idx = bot.user_data[user_id]['current_track'] - 1
    bot.user_data[user_id]['tracks'][current_track_idx]['producer'] = message.text

    bot.send_message(
        message.chat.id,
        "8) Жанр трека:\n\n"
        "🎼 Укажите музыкальный жанр этого трека:\n\n"
        "💡 Популярные жанры:\n"
        "• Hip-Hop, Rap, Trap\n"
        "• Pop, Dance, House\n"
        "• Rock, Alternative, Indie\n"
        "• R&B, Soul, Jazz\n"
        "• Electronic, Techno, Dubstep\n\n"
        "📝 Введите один основной жанр:",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, process_track_genre)

def process_track_genre(message):
    """Обработка жанра трека с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    user_id = message.from_user.id
    current_track_idx = bot.user_data[user_id]['current_track'] - 1
    bot.user_data[user_id]['tracks'][current_track_idx]['genre'] = message.text

    ask_track_audio(message)

def ask_track_audio(message):
    """Запрос аудио трека с кнопкой отмены"""
    user_id = message.from_user.id
    current_track = bot.user_data[user_id]['current_track']

    bot.send_message(
        message.chat.id,
        f"9) Аудиофайл для трека {current_track} (WAV, STEREO):\n\n"
        "Загрузите 1 файл поддерживаемого типа: audio. Размер файла – не более 100 MB.",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, process_track_audio)

def ask_track_contract(message):
    """Запрос договора на бит для текущего трека"""
    user_id = message.from_user.id
    current_track = bot.user_data[user_id]['current_track']

    bot.send_message(
        message.chat.id,
        f"9.1) ДОГОВОР НА БИТ для трека {current_track}\n\n"
        "Загрузите 1 файл поддерживаемого типа. Размер файла – не более 10 MB.",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, process_track_contract)

def process_track_contract(message):
    """Обработка договора на бит для текущего трека"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    # Используем универсальную функцию валидации
    is_valid, error_message, file_id = validate_file_upload(
        message,
        allowed_extensions=['.pdf', '.doc', '.docx', '.jpg', '.png'],
        max_size_mb=10,
        required_type="document"
    )

    if not is_valid:
        msg = bot.send_message(
            message.chat.id,
            error_message,
            reply_markup=create_cancel_keyboard()
        )
        bot.register_next_step_handler(msg, process_track_contract)
        return

    user_id = message.from_user.id
    current_track_idx = bot.user_data[user_id]['current_track'] - 1
    bot.user_data[user_id]['tracks'][current_track_idx]['contract_file_id'] = file_id

    # После договора — спросим текст для ТЕКУЩЕГО трека
    ask_track_lyrics(message)

def ask_track_lyrics(message):
    """Запрос текста (TXT-файл) для текущего трека"""
    user_id = message.from_user.id
    current_track = bot.user_data[user_id]['current_track']

    bot.send_message(
        message.chat.id,
        f"9.2) Текст трека {current_track} файлом в формате .txt:",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, process_track_lyrics)

def process_track_lyrics(message):
    """Обработка текста трека (ожидаем документ txt)"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    user_id = message.from_user.id
    current_track_idx = bot.user_data[user_id]['current_track'] - 1

    # Используем универсальную функцию валидации
    is_valid, error_message, file_id = validate_file_upload(
        message,
        allowed_extensions=['.txt'],
        max_size_mb=10,
        required_type="document"
    )

    if not is_valid:
        msg = bot.send_message(
            message.chat.id,
            error_message,
            reply_markup=create_cancel_keyboard()
        )
        bot.register_next_step_handler(msg, process_track_lyrics)
        return

    # Сохраняем file_id текста трека
    bot.user_data[user_id]['tracks'][current_track_idx]['lyrics_file_id'] = file_id

    # Переход к следующему треку или завершение
    bot.user_data[user_id]['current_track'] += 1
    track_count = bot.user_data[user_id]['track_count']

    if bot.user_data[user_id]['current_track'] <= track_count:
        ask_track_info(message)
    else:
        ask_album_cover(message)

def ask_album_cover(message):
    """Запрос обложки альбома с кнопкой отмены"""
    bot.send_message(
        message.chat.id,
        "10) Обложка альбома (PNG, JPG 3000x3000):\n\n"
        "🎨 Способы отправки обложки:\n"
        "📷 Как фото (быстро, сжатое)\n"
        "📎 Как документ (лучшее качество, несжатое)\n\n"
        "💡 Для лучшего качества ОБЯЗАТЕЛЬНО отправляйте как документ:\n"
        "• Нажмите на скрепку 📎\n"
        "• Выберите 'Файл' или 'Документ'\n"
        "• Выберите файл обложки\n\n"
        "⚠️ ВАЖНО: Отправка как фото значительно снижает качество!\n"
        "✅ Поддерживаемые форматы: PNG, JPG, JPEG, WEBP\n"
        "📐 Рекомендуемый размер: 3000x3000 пикселей\n"
        "💾 Максимальный размер файла: 100 MB",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, process_album_cover)

def process_album_cover(message):
    """Обработка обложки альбома с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    user_id = message.from_user.id

    try:
        if message.photo:
            # Принимаем сжатые изображения (фото)
            file_id = message.photo[-1].file_id
            logger.info(f"Received album photo cover, file_id: {file_id}")

            # Проверяем и инициализируем user_data если нужно
            if user_id not in bot.user_data:
                logger.warning(f"User data not found for user {user_id}, reinitializing")
                bot.user_data[user_id] = {}

            bot.user_data[user_id]['cover_file_id'] = file_id
            bot.user_data[user_id]['cover_file_type'] = 'photo'  # Сохраняем тип файла
            logger.info(f"Saved album photo cover_file_id for user {user_id}: {file_id}")
            debug_user_data(user_id, "after_album_photo_cover")

            bot.send_message(
                message.chat.id,
                "✅ Обложка принята как фото!"
            )
            ask_album_release_date(message)
            return

        elif message.document:
            file_name = (message.document.file_name or '').lower()
            mime_type = (message.document.mime_type or '').lower()

            allowed_extensions = ['.png', '.jpg', '.jpeg', '.webp']
            # Проверяем MIME-тип, расширение файла и размер
            if (mime_type.startswith('image/') or any(file_name.endswith(ext) for ext in allowed_extensions)) and message.document.file_size <= 100 * 1024 * 1024:  # 100 MB
                file_id = message.document.file_id
                logger.info(f"Received album document cover: {file_name} ({mime_type}), file_id: {file_id}")

                # Проверяем и инициализируем user_data если нужно
                if user_id not in bot.user_data:
                    logger.warning(f"User data not found for user {user_id}, reinitializing")
                    bot.user_data[user_id] = {}

                bot.user_data[user_id]['cover_file_id'] = file_id
                bot.user_data[user_id]['cover_file_type'] = 'document'  # Сохраняем тип файла
                logger.info(f"Saved album cover_file_id for user {user_id}: {file_id}")
                debug_user_data(user_id, "after_album_document_cover")

                bot.send_message(
                    message.chat.id,
                    "✅ Обложка принята как документ (качество сохранено)!"
                )
                ask_album_release_date(message)
                return

        # Проверяем размер файла отдельно для более точного сообщения об ошибке
        if message.document and message.document.file_size > 100 * 1024 * 1024:
            error_msg = (
                "❌ Файл слишком большой!\n\n"
                f"📏 Размер файла: {message.document.file_size / (1024 * 1024):.1f} МБ\n"
                "💾 Максимальный размер: 100 МБ\n\n"
                "💡 Рекомендации:\n"
                "• Сожмите изображение до размера менее 100 МБ\n"
                "• Используйте формат JPG вместо PNG для уменьшения размера\n"
                "• Отправьте как фото (📷) для автоматического сжатия\n\n"
                "Попробуйте отправить обложку еще раз:"
            )
        else:
            error_msg = (
                "❌ Неверный формат обложки!\n\n"
                "Поддерживаемые способы отправки:\n"
                "📷 Как фото (сжатое)\n"
                "📎 Как документ (несжатое, лучшее качество)\n\n"
                "✅ Поддерживаемые форматы: PNG, JPG, JPEG, WEBP\n"
                "💾 Максимальный размер: 100 МБ\n\n"
                "Пожалуйста, отправьте обложку в правильном формате:"
        )
        msg = bot.send_message(message.chat.id, error_msg, reply_markup=create_cancel_keyboard())
        bot.register_next_step_handler(msg, process_album_cover)

    except Exception as e:
        logger.error(f"Ошибка обработки обложки: {str(e)}")
        error_msg = (
            "❌ Ошибка обработки файла!\n\n"
            "Проверьте что файл:\n"
            "• Является изображением\n"
            "• Имеет размер менее 100 МБ\n"
            "• Имеет правильный формат (PNG/JPG/JPEG/WEBP)\n\n"
            "💡 Рекомендации:\n"
            "• Для лучшего качества отправляйте как документ (📎)\n"
            "• Для быстрой загрузки отправляйте как фото (📷)\n"
            "• Убедитесь, что файл не поврежден\n\n"
            "Попробуйте отправить обложку еще раз:"
        )
        msg = bot.send_message(message.chat.id, error_msg, reply_markup=create_cancel_keyboard())
        bot.register_next_step_handler(msg, process_album_cover)

def ask_album_release_date(message):
    """Запрос даты релиза альбома с кнопкой отмены"""
    bot.send_message(
        message.chat.id,
        "11) Дата релиза альбома (в формате ДД.ММ.ГГГГ):\n\n"
        "📅 Укажите дату выхода вашего альбома:\n\n"
        "💡 Формат: ДД.ММ.ГГГГ (например: 15.03.2024)\n\n"
        "⚠️ Важные моменты:\n"
        "• Дата должна быть в будущем\n"
        "• Для промо поддержки подавайте заявку за 2 недели до релиза\n"
        "• Учитывайте время обработки альбома (7-14 дней)\n"
        "• Все треки альбома выйдут в эту дату\n\n"
        "📝 Введите дату релиза альбома:",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, process_album_release_date)

def process_album_release_date(message):
    """Обработка даты релиза альбома с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    try:
        release_date = datetime.strptime(message.text, "%d.%m.%Y").date()
        user_id = message.from_user.id
        bot.user_data[user_id]['release_date'] = release_date
        ask_performer_name(message)
    except ValueError:
        msg = bot.send_message(
            message.chat.id,
            "Неверный формат даты. Используйте ДД.ММ.ГГГГ",
            reply_markup=create_cancel_keyboard()
        )
        bot.register_next_step_handler(msg, process_album_release_date)

def process_track_audio(message):
    """Process audio file for track and then ask for track contract"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    if not message.audio and not message.document:
        msg = bot.send_message(message.chat.id, "Пожалуйста, загрузите аудиофайл")
        bot.register_next_step_handler(msg, process_track_audio)
        return

    user_id = message.from_user.id
    current_track_idx = bot.user_data[user_id]['current_track'] - 1

    # Save audio file ID
    if message.audio:
        file_id = message.audio.file_id
    else:
        file_id = message.document.file_id

    bot.user_data[user_id]['tracks'][current_track_idx]['audio_file_id'] = file_id

    # After audio, ask for contract for this track
    ask_track_contract(message)

def ask_artist_name(message):
    """Запрос имени артиста с кнопкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)
    bot.user_data[message.from_user.id] = {'release_type': message.text}
    bot.send_message(
        message.chat.id,
        "3) Исполнитель(-и):\n\n"
        "🎤 Укажите основного исполнителя или группу:\n\n"
        "💡 Примеры:\n"
        "• \"Артист Исполнитель\"\n"
        "• \"The Music Band\"\n"
        "• \"Singer feat. Rapper\"\n\n"
        "📝 Если несколько исполнителей, перечислите через запятую:",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, ask_release_name)

def ask_release_name(message):
    """Запрос названия релиза с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    try:
        bot.user_data[message.from_user.id]['artist_name'] = message.text
        bot.send_message(
            message.chat.id,
            "4) Название релиза:\n\n"
            "🎵 Введите название вашего сингла:\n\n"
            "💡 Примеры:\n"
            "• \"Моя Лучшая Песня\"\n"
            "• \"Summer Hit 2024\"\n"
            "• \"Love Ballad (Radio Edit)\"\n\n"
            "📝 Название должно соответствовать аудиофайлу:",
            reply_markup=create_cancel_keyboard()
        )
        bot.register_next_step_handler(message, ask_producer)
    except Exception as e:
        logger.error(f"Error in ask_release_name: {e}")
        bot.send_message(message.chat.id, "Произошла ошибка, пожалуйста, попробуйте снова.")

def cancel_distribution(message):
    """Отмена процесса создания релиза"""
    user_id = message.from_user.id
    if user_id in bot.user_data:
        # Очищаем только контекст создания релиза, оставляя возможные pending операции
        for key in list(bot.user_data[user_id].keys()):
            if key not in ('pending_operation',):
                bot.user_data[user_id].pop(key, None)
    bot.send_message(message.chat.id, "❌ Процесс создания релиза отменён.", reply_markup=create_main_menu())

def create_cancel_keyboard():
    """Создает клавиатуру с кнопками отмены и сохранения черновика"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(
        types.KeyboardButton("💾 Сохранить черновик"),
        types.KeyboardButton("❌ Отмена")
    )
    return markup

def create_options_keyboard(options):
    """Создает клавиатуру с опциями, кнопкой отмены и сохранения черновика"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [types.KeyboardButton(option) for option in options]
    markup.add(*buttons)
    markup.add(
        types.KeyboardButton("💾 Сохранить черновик"),
        types.KeyboardButton("❌ Отмена")
    )
    return markup

def ask_producer(message):
    """Запрос продюсера с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    bot.user_data[message.from_user.id]['release_name'] = message.text
    bot.send_message(
        message.chat.id,
        "5) prod. by (будет указан в формате [prod.by yourbeatmaker]):\n\n"
        "🎛️ Укажите продюсера/битмейкера:\n\n"
        "💡 Примеры:\n"
        "• \"BeatMaker\"\n"
        "• \"ProducerName\"\n"
        "• \"YourBeatMaker\"\n\n"
        "📝 Будет отображаться как: [prod.by ВашПродюсер]",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, ask_genre)

def ask_genre(message):
    """Запрос жанра с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    bot.user_data[message.from_user.id]['producer'] = message.text
    bot.send_message(
        message.chat.id,
        "6) Жанр релиза:\n\n"
        "🎼 Укажите музыкальный жанр вашего релиза:\n\n"
        "💡 Популярные жанры:\n"
        "• Hip-Hop, Rap, Trap\n"
        "• Pop, Dance, House\n"
        "• Rock, Alternative, Indie\n"
        "• R&B, Soul, Jazz\n"
        "• Electronic, Techno, Dubstep\n\n"
        "📝 Введите один основной жанр:",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, process_genre)

def process_genre(message):
    """Обработка жанра с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    bot.user_data[message.from_user.id]['genre'] = message.text
    ask_cover(message)

def ask_cover(message):
    """Запрос обложки с кнопкой отмены"""
    bot.send_message(
        message.chat.id,
        "7) Обложка релиза (PNG, JPG 3000x3000):\n\n"
        "🎨 Способы отправки обложки:\n"
        "📷 Как фото (быстро, сжатое)\n"
        "📎 Как документ (лучшее качество, несжатое)\n\n"
        "💡 Для лучшего качества ОБЯЗАТЕЛЬНО отправляйте как документ:\n"
        "• Нажмите на скрепку 📎\n"
        "• Выберите 'Файл' или 'Документ'\n"
        "• Выберите файл обложки\n\n"
        "⚠️ ВАЖНО: Отправка как фото значительно снижает качество!\n"
        "✅ Поддерживаемые форматы: PNG, JPG, JPEG, WEBP\n"
        "📐 Рекомендуемый размер: 3000x3000 пикселей\n"
        "💾 Максимальный размер файла: 100 MB",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, process_cover)

def process_cover(message):
    """Обработка обложки с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    user_id = message.from_user.id
    if user_id not in bot.user_data:
        bot.send_message(message.chat.id, "❌ Сессия создания релиза устарела. Начните заново.")
        return

    try:
        if message.photo:
            file_id = message.photo[-1].file_id
            logger.info(f"Received photo cover: {file_id}")

            # Проверяем и инициализируем user_data если нужно
            if user_id not in bot.user_data:
                logger.warning(f"User data not found for user {user_id}, reinitializing")
                bot.user_data[user_id] = {}

            bot.user_data[user_id]['cover_file_id'] = file_id
            bot.user_data[user_id]['cover_file_type'] = 'photo'  # Сохраняем тип файла
            logger.info(f"Saved photo cover_file_id for user {user_id}: {file_id}")
            debug_user_data(user_id, "after_single_photo_cover")

            bot.send_message(
                message.chat.id,
                "✅ Обложка принята как фото!"
            )
            ask_audio(message)
            return

        elif message.document:
            file_name = (message.document.file_name or '').lower()
            mime_type = (message.document.mime_type or '').lower()

            allowed_extensions = ['.png', '.jpg', '.jpeg', '.webp']
            if (mime_type.startswith('image/') or any(file_name.endswith(ext) for ext in allowed_extensions)) and message.document.file_size <= 100 * 1024 * 1024:  # 100 MB
                file_id = message.document.file_id
                logger.info(f"Received document cover: {file_name} ({mime_type}), file_id: {file_id}")

                # Проверяем и инициализируем user_data если нужно
                if user_id not in bot.user_data:
                    logger.warning(f"User data not found for user {user_id}, reinitializing")
                    bot.user_data[user_id] = {}

                bot.user_data[user_id]['cover_file_id'] = file_id
                bot.user_data[user_id]['cover_file_type'] = 'document'  # Сохраняем тип файла
                logger.info(f"Saved cover_file_id for user {user_id}: {file_id}")
                debug_user_data(user_id, "after_single_document_cover")

                bot.send_message(
                    message.chat.id,
                    "✅ Обложка принята как документ (качество сохранено)!"
                )
                ask_audio(message)
                return

        # Проверяем размер файла отдельно для более точного сообщения об ошибке
        if message.document and message.document.file_size > 100 * 1024 * 1024:
            error_msg = (
                "❌ Файл слишком большой!\n\n"
                f"📏 Размер файла: {message.document.file_size / (1024 * 1024):.1f} МБ\n"
                "💾 Максимальный размер: 100 МБ\n\n"
                "💡 Рекомендации:\n"
                "• Сожмите изображение до размера менее 100 МБ\n"
                "• Используйте формат JPG вместо PNG для уменьшения размера\n"
                "• Отправьте как фото (📷) для автоматического сжатия\n\n"
                "Попробуйте отправить обложку еще раз:"
            )
        else:
            error_msg = (
                "❌ Неверный формат обложки!\n\n"
                "Поддерживаемые способы отправки:\n"
                "📷 Как фото (сжатое)\n"
                "📎 Как документ (несжатое, лучшее качество)\n\n"
                "✅ Поддерживаемые форматы: PNG, JPG, JPEG, WEBP\n"
                "💾 Максимальный размер: 100 МБ\n\n"
                "Пожалуйста, отправьте обложку в правильном формате:"
        )
        msg = bot.send_message(message.chat.id, error_msg, reply_markup=create_cancel_keyboard())
        bot.register_next_step_handler(msg, process_cover)

    except Exception as e:
        logger.error(f"Error processing cover: {str(e)}")
        error_msg = (
            "❌ Ошибка обработки файла!\n\n"
            "Проверьте что файл:\n"
            "• Является изображением\n"
            "• Имеет размер менее 100 МБ\n"
            "• Имеет правильный формат (PNG/JPG/JPEG/WEBP)\n\n"
            "💡 Рекомендации:\n"
            "• Для лучшего качества отправляйте как документ (📎)\n"
            "• Для быстрой загрузки отправляйте как фото (📷)\n"
            "• Убедитесь, что файл не поврежден\n\n"
            "Попробуйте отправить обложку еще раз:"
        )
        msg = bot.send_message(message.chat.id, error_msg, reply_markup=create_cancel_keyboard())
        bot.register_next_step_handler(msg, process_cover)

def ask_audio(message):
    """Запрос аудиофайла с кнопкой отмены"""
    bot.send_message(
        message.chat.id,
        "8) Файл трека (WAV, STEREO):\n\n"
        "🎧 Загрузите аудиофайл вашего трека:\n\n"
        "💡 Рекомендуемые форматы:\n"
        "• WAV (несжатый, лучшее качество)\n"
        "• MP3 (сжатый, меньший размер)\n"
        "• FLAC (сжатый без потерь)\n\n"
        "⚙️ Технические требования:\n"
        "• Формат: STEREO (стерео)\n"
        "• Качество: не менее 44.1 kHz / 16 bit\n"
        "• Максимальный размер: 100 MB\n\n"
        "📎 Отправьте файл как документ для сохранения качества:",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, process_audio)

def process_audio(message):
    """Обработка аудиофайла с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    if not message.audio and not message.document:
        msg = bot.send_message(
            message.chat.id,
            "Пожалуйста, загрузите аудиофайл",
            reply_markup=create_cancel_keyboard()
        )
        bot.register_next_step_handler(msg, process_audio)
        return

    if message.audio:
        file_id = message.audio.file_id
    else:
        file_id = message.document.file_id

    bot.user_data[message.from_user.id]['audio_file_id'] = file_id
    ask_release_date(message)

def ask_release_date(message):
    """Запрос даты релиза с кнопкой отмены"""
    bot.send_message(
        message.chat.id,
        "9) Дата релиза (в формате ДД.ММ.ГГГГ):\n\n"
        "📅 Укажите дату выхода вашего релиза:\n\n"
        "💡 Формат: ДД.ММ.ГГГГ (например: 25.12.2024)\n\n"
        "⚠️ Важные моменты:\n"
        "• Дата должна быть в будущем\n"
        "• Для промо поддержки подавайте заявку за 2 недели до релиза\n"
        "• Учитывайте время обработки заявки (3-7 дней)\n\n"
        "📝 Введите дату релиза:",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, process_release_date)

def process_release_date(message):
    """Обработка даты релиза с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    try:
        release_date = datetime.strptime(message.text, "%d.%m.%Y").date()
        bot.user_data[message.from_user.id]['release_date'] = release_date
        ask_performer_name(message)
    except ValueError:
        msg = bot.send_message(
            message.chat.id,
            "Неверный формат даты. Используйте ДД.ММ.ГГГГ",
            reply_markup=create_cancel_keyboard()
        )
        bot.register_next_step_handler(msg, process_release_date)

def ask_performer_name(message):
    """Запрос ФИО исполнителя с кнопкой отмены"""
    bot.send_message(
        message.chat.id,
        "10) ФИО Исполнителя (-ей):\n\n"
        "👤 Укажите полное имя исполнителя для официальных документов:\n\n"
        "💡 Примеры:\n"
        "• \"Иванов Иван Иванович\"\n"
        "• \"Петрова Анна Сергеевна\"\n"
        "• \"Smith John Michael\"\n\n"
        "📝 Важно:\n"
        "• Указывайте реальное ФИО (как в паспорте)\n"
        "• Если несколько исполнителей, перечислите через запятую\n"
        "• Эта информация нужна для договоров с площадками:",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, ask_music_author)

def ask_music_author(message):
    """Запрос автора музыки с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    bot.user_data[message.from_user.id]['performer_name'] = message.text
    bot.send_message(
        message.chat.id,
        "11) ФИО Автора (-ов) музыки:\n\n"
        "🎼 Укажите автора(ов) музыкальной композиции:\n\n"
        "💡 Примеры:\n"
        "• \"Композиторов Алексей Владимирович\"\n"
        "• \"Musicmaker Ivan Petrov\"\n"
        "• \"Иванов И.И., Петров П.П.\"\n\n"
        "📝 Важные моменты:\n"
        "• Автор музыки - тот, кто создал мелодию\n"
        "• Может отличаться от исполнителя\n"
        "• Если несколько авторов, перечислите через запятую\n"
        "• Указывайте полные ФИО для авторских прав:",
        reply_markup=create_cancel_keyboard()
    )
    # Всегда следующим шагом обрабатываем авторов в функции ask_contract,
    # где будет ветвление: для мульти-трековых релизов пропускаем запрос договора
    bot.register_next_step_handler(message, ask_contract)

def ask_contract(message):
    """Запрос договора с кнопкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    user_id = message.from_user.id
    bot.user_data[user_id]['music_author'] = message.text
    release_type = bot.user_data.get(user_id, {}).get('release_type')

    # Для мульти-трековых релизов пропускаем запрос договора на уровне альбома — договоры собираются по трекам
    if release_type in ("ALBUM", "EP", "Maxi Single"):
        ask_videoshot(message)
        return

    bot.send_message(
        message.chat.id,
        "12) ДОГОВОР НА БИТ\n\n"
        "📄 Загрузите договор на использование бита:\n\n"
        "💡 Что это:\n"
        "• Документ, подтверждающий права на использование инструментала\n"
        "• Договор с битмейкером/продюсером\n"
        "• Лицензия на бит\n\n"
        "📎 Форматы файлов:\n"
        "• PDF, DOC, DOCX, JPG, PNG\n"
        "• Максимальный размер: 10 MB\n\n"
        "⚠️ Важно: без этого документа релиз не может быть опубликован на площадках:",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, process_contract)

def process_contract(message):
    """Обработка договора с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    # Используем универсальную функцию валидации
    is_valid, error_message, file_id = validate_file_upload(
        message,
        allowed_extensions=['.pdf', '.doc', '.docx', '.jpg', '.png'],
        max_size_mb=10,
        required_type="document"
    )

    if not is_valid:
        msg = bot.send_message(
            message.chat.id,
            error_message,
            reply_markup=create_cancel_keyboard()
        )
        bot.register_next_step_handler(msg, process_contract)
        return

    bot.user_data[message.from_user.id]['contract_file_id'] = file_id
    ask_videoshot(message)

def ask_videoshot(message):
    """Запрос видеошота с кнопкой отмены"""
    bot.send_message(
        message.chat.id,
        "13) Ссылка на видеошот для Яндекс.Музыки (если нет, напишите 'нет'):\n\n"
        "🎥 Видеошот - короткий вертикальный клип для промо:\n\n"
        "💡 Что это:\n"
        "• Короткое видео (15-30 сек) в вертикальном формате\n"
        "• Используется для продвижения в Яндекс.Музыке\n"
        "• Может содержать отрывок трека + визуал\n\n"
        "📎 Как отправить:\n"
        "• Загрузите видео на YouTube, VK, или другую платформу\n"
        "• Отправьте ссылку на видео\n"
        "• Если видеошота нет, напишите 'нет'\n\n"
        "📝 Введите ссылку или 'нет':",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, ask_explicit_content)

def process_explicit_response(message):
    """Обработка контента для взрослых с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    user_id = message.from_user.id
    bot.user_data[user_id]['explicit_content'] = message.text.lower() == 'да'

    # Для многотрековых форматов (ALBUM, EP, Maxi Single) текст треков уже собран по каждому треку,
    # поэтому переходим сразу к следующему шагу без вопроса "15) Текст трека ..."
    if bot.user_data[user_id].get('release_type') in ['ALBUM', 'EP', 'Maxi Single']:
        ask_preview_start(message)
    else:
        ask_lyrics(message)

def ask_explicit_content(message):
    """Запрос контента для взрослых с кнопкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    user_id = message.from_user.id
    bot.user_data[user_id]['videoshot_url'] = message.text if message.text.lower() != 'нет' else None

    markup = create_options_keyboard(["Да", "Нет"])
    msg = bot.send_message(
        message.chat.id,
        "14) Нецензурная лексика в треке (маты):",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, process_explicit_response)

def ask_lyrics(message):
    """Запрос текста песни с кнопкой отмены"""
    bot.send_message(
        message.chat.id,
        "15) Текст трека файлом в формате txt:",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, process_lyrics)

def process_lyrics(message):
    """Обработка текста песни с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    # Используем универсальную функцию валидации
    is_valid, error_message, file_id = validate_file_upload(
        message,
        allowed_extensions=['.txt'],
        max_size_mb=10,
        required_type="document"
    )

    if not is_valid:
        msg = bot.send_message(
            message.chat.id,
            error_message,
            reply_markup=create_cancel_keyboard()
        )
        bot.register_next_step_handler(msg, process_lyrics)
        return

    bot.user_data[message.from_user.id]['lyrics_file_id'] = file_id
    ask_preview_start(message)

def ask_preview_start(message):
    """Запрос времени предпрослушивания с кнопкой отмены"""
    bot.send_message(
        message.chat.id,
        "16) Начало предпрослушивания (секунда начала звука, например 90 для 1:30):",
        reply_markup=create_cancel_keyboard()
    )
    bot.register_next_step_handler(message, ask_yandex_soon)

def ask_yandex_soon(message):
    """Запрос плашки 'Скоро' с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    try:
        bot.user_data[message.from_user.id]['preview_start'] = int(message.text)
        markup = create_options_keyboard(["Да", "Нет"])
        msg = bot.send_message(
            message.chat.id,
            "17) Плашка 'скоро новый релиз' на Яндекс.Музыке:",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, ask_create_links)
    except ValueError:
        msg = bot.send_message(
            message.chat.id,
            "Пожалуйста, введите число (секунды)",
            reply_markup=create_cancel_keyboard()
        )
        bot.register_next_step_handler(msg, ask_yandex_soon)

def ask_create_links(message):
    """Запрос создания ссылок с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    bot.user_data[message.from_user.id]['yandex_soon'] = message.text.lower() == 'да'
    markup = create_options_keyboard(["Да", "Нет"])
    msg = bot.send_message(
        message.chat.id,
        "18) Сделать ссылку на все площадки?",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, ask_tiktok_features)

def ask_tiktok_features(message):
    """Запрос функций TikTok с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    bot.user_data[message.from_user.id]['create_links'] = message.text.lower() == 'да'
    markup = create_options_keyboard(["Да", "Нет"])
    msg = bot.send_message(
        message.chat.id,
        "19) Разрешить коммерческое использование в TikTok?",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, process_tiktok_commercial)

def process_tiktok_commercial(message):
    """Обработка коммерческого использования TikTok с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    bot.user_data[message.from_user.id]['tiktok_commercial'] = message.text.lower() == 'да'
    markup = create_options_keyboard(["Да", "Нет"])
    msg = bot.send_message(
        message.chat.id,
        "20) Разрешить полную версию трека в TikTok?",
        reply_markup=markup
    )
    bot.register_next_step_handler(msg, process_tiktok_full_version)

def process_tiktok_full_version(message):
    """Обработка полной версии в TikTok с проверкой отмены"""
    if is_cancel_message(message):
        return cancel_distribution(message)

    user_id = message.from_user.id
    bot.user_data[user_id]['tiktok_full_version'] = message.text.lower() == 'да'

    # Вместо сохранения показываем предварительный просмотр (сохраняем клавиатуру «из черновика», если заходили из профиля)
    ud = bot.user_data[user_id]
    show_release_preview(message, ud, from_draft=ud.get('from_draft', False))

def show_release_preview(message, user_data, from_draft=False):
    """Показывает предварительный просмотр релиза перед сохранением. from_draft=True — заход из профиля (Черновики)."""
    preview_text = "📝 ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР РЕЛИЗА 📝\n\n"

    if user_data.get('release_type') == 'ALBUM':
        # Формирование текста для альбома
        preview_text += f"💿 Тип: Альбом ({user_data['release_type']})\n"
        preview_text += f"🎤 Исполнитель альбома: {user_data.get('album_artist', 'не указано')}\n"
        preview_text += f"📀 Название альбома: {user_data.get('album_name', 'не указано')}\n"
        preview_text += f"📅 Дата релиза: {user_data.get('release_date', 'не указана')}\n"
        preview_text += f"🎵 Количество треков: {user_data.get('track_count', 0)}\n\n"

        preview_text += "🎧 Треки:\n"
        for i, track in enumerate(user_data.get('tracks', []), 1):
            preview_text += f"{i}. {track.get('track_name', 'без названия')} "
            preview_text += f"(prod. {track.get('producer', 'не указан')}) - "
            preview_text += f"{track.get('genre', 'жанр не указан')}\n"
    else:
        # Формирование текста для сингла
        preview_text += f"🎵 Тип: {user_data.get('release_type', 'не указан')}\n"
        preview_text += f"🎤 Исполнитель: {user_data.get('artist_name', 'не указан')}\n"
        preview_text += f"📀 Название релиза: {user_data.get('release_name', 'не указано')}\n"
        preview_text += f"🎹 Продюсер: {user_data.get('producer', 'не указан')}\n"
        preview_text += f"🎼 Жанр: {user_data.get('genre', 'не указан')}\n"
        preview_text += f"📅 Дата релиза: {user_data.get('release_date', 'не указана')}\n"
        preview_text += f"👤 ФИО Исполнителя: {user_data.get('performer_name', 'не указано')}\n"
        preview_text += f"✍️ Автор музыки: {user_data.get('music_author', 'не указано')}\n"
        preview_text += f"🔞 Эксплисит контент: {'Да' if user_data.get('explicit_content') else 'Нет'}\n"
        preview_text += f"🕒 Начало превью: {user_data.get('preview_start', 'не указано')} сек.\n"
        preview_text += f"🟢 Яндекс 'Скоро': {'Да' if user_data.get('yandex_soon') else 'Нет'}\n"
        preview_text += f"🔗 Создать ссылки: {'Да' if user_data.get('create_links') else 'Нет'}\n"
        preview_text += f"📱 TikTok коммерч.: {'Да' if user_data.get('tiktok_commercial') else 'Нет'}\n"
        preview_text += f"🎵 TikTok полная версия: {'Да' if user_data.get('tiktok_full_version') else 'Нет'}\n"
    user_id = message.from_user.id
    conn = get_pg_connection()
    is_artist = False

    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('SELECT artist FROM label WHERE telegram_id = %s', (user_id,))
            result = cursor.fetchone()
            if result and result[0] == 1:
                is_artist = True
        except Exception:
            pass
        finally:
            return_pg_connection(conn)

    # Расчёт стоимости
    cost_text = ""
    release_type = user_data.get('release_type')
    if is_artist:
        total_cost = 0
        cost_text = "\n\n🎉 БЕСПЛАТНО! У вас статус Artist"
    else:
        if release_type == "Single":
            total_cost = 1299
            cost_text = f"\n\n💵 Стоимость: 1299₽ (Single)"
        elif release_type == "Maxi Single":
            total_cost = 1799
            cost_text = f"\n\n💵 Стоимость: 1799₽ (Maxi Single)"
        elif release_type == "EP":
            total_cost = 2399
            cost_text = f"\n\n💵 Стоимость: 2399₽ (EP)"
        elif release_type == "ALBUM":
            total_cost = 2899
            cost_text = f"\n\n💵 Стоимость: 2899₽ (Альбом)"
        else:
            total_cost = 1299
            cost_text = ""

    if not hasattr(bot, 'user_data'):
        bot.user_data = {}
    bot.user_data[user_id]['calculated_cost'] = total_cost
    bot.user_data[user_id]['is_artist'] = is_artist
    bot.user_data[user_id]['from_draft'] = from_draft

    preview_text += cost_text
    preview_text += "\n\nВсё верно? Подтвердите сохранение релиза."

    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    if is_artist:
        markup.add("✅ Отправить бесплатно")
    else:
        markup.add("✅ Оплатить и отправить")
    if not from_draft:
        markup.add("💾 Сохранить как черновик")
    markup.add("✏️ Нет, изменить данные")
    markup.add("◀️ Назад в меню" if from_draft else "❌ Отменить создание")

    bot.send_message(message.chat.id, preview_text, reply_markup=markup)

    release_type = user_data.get("release_type")
    tracks = user_data.get("tracks") or []

    # Альбом / EP / Maxi Single с несколькими треками — название трека отдельным сообщением, под ним кнопка «Посмотреть вложения»
    if release_type in ("ALBUM", "EP", "Maxi Single") and tracks:
        if user_data.get("cover_file_id"):
            attach_m = types.InlineKeyboardMarkup()
            attach_m.add(types.InlineKeyboardButton("🖼 Обложка релиза", callback_data="preview_cover"))
            bot.send_message(message.chat.id, "📎 Обложка релиза:", reply_markup=attach_m)
        for i, track in enumerate(tracks):
            track_name = track.get("track_name") or f"Трек {i + 1}"
            # Название трека — отдельное сообщение
            bot.send_message(message.chat.id, f"🎵 Трек {i + 1}: {track_name}")
            # Под ним — кнопка «Посмотреть вложения» (отправит все вложения трека и аудио)
            track_markup = types.InlineKeyboardMarkup()
            track_markup.add(types.InlineKeyboardButton("📎 Посмотреть вложения", callback_data=f"preview_track_{i}"))
            bot.send_message(message.chat.id, "📎 Вложения трека:", reply_markup=track_markup)
    else:
        # Сингл — одна кнопка «Посмотреть вложения» (обложка, трек, договор)
        attach_buttons = []
        if user_data.get("cover_file_id"):
            attach_buttons.append(types.InlineKeyboardButton("🖼 Обложка", callback_data="preview_cover"))
        if user_data.get("audio_file_id"):
            attach_buttons.append(types.InlineKeyboardButton("🎵 Трек", callback_data="preview_audio"))
        if user_data.get("contract_file_id"):
            attach_buttons.append(types.InlineKeyboardButton("📄 Договор", callback_data="preview_contract"))
        if attach_buttons:
            attach_markup = types.InlineKeyboardMarkup(row_width=2)
            attach_markup.add(*attach_buttons)
            bot.send_message(
                message.chat.id,
                "📎 Посмотреть вложения:",
                reply_markup=attach_markup
            )

    bot.register_next_step_handler(message, process_preview_confirmation)

def process_preview_confirmation(message):
    """Обрабатывает подтверждение предварительного просмотра"""
    user_id = message.from_user.id
    user_data = bot.user_data.get(user_id, {})

    if message.text == "✅ Оплатить и отправить":
        # Предложим подтвердить списание и перейти к оплате
        total_cost = user_data.get('calculated_cost', 1299)
        release_type = user_data.get('release_type', 'Single')
        bot.user_data.setdefault(user_id, {})['calculated_cost'] = total_cost
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Подтвердить оплату", callback_data=f"distribution_pay_{total_cost}"))
        markup.add(types.InlineKeyboardButton("🎟 Использовать промокод", callback_data="use_promo_distribution"))
        bot.send_message(
            message.chat.id,
            f"Подтвердите списание {total_cost}₽ за {release_type}.",
            reply_markup=markup
        )
    elif message.text == "✅ Отправить бесплатно":
        # Для пользователей со статусом artist - сразу сохраняем релиз.
        # Текст кнопки можно отправить вручную, поэтому роль проверяем по базе.
        is_artist = False
        conn = get_pg_connection()
        if conn:
            cursor = conn.cursor()
            try:
                is_artist = _user_is_artist(cursor, user_id)
            finally:
                cursor.close()
                return_pg_connection(conn)
        if not is_artist:
            bot.send_message(message.chat.id, "❌ Бесплатная отправка доступна только артистам лейбла. Выберите «✅ Оплатить и отправить».")
            bot.register_next_step_handler(message, process_preview_confirmation)
            return
        bot.send_message(
            message.chat.id,
            "🎉 Отправляем релиз бесплатно! Сохраняем данные...",
            reply_markup=types.ReplyKeyboardRemove()
        )
        save_release_data_for_user(user_id, message.chat.id)
    elif message.text == "💾 Сохранить как черновик":
        try:
            conn = get_pg_connection()
            if conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO drafts (user_id, draft_type, data, current_step, created_at, updated_at) VALUES (%s, %s, %s, %s, NOW(), NOW())',
                    (message.from_user.id, 'distribution_legacy', json.dumps(user_data, ensure_ascii=False, default=str), 0)
                )
                conn.commit()
                cursor.close()
                return_pg_connection(conn)
            bot.user_data.pop(message.from_user.id, None)
            bot.send_message(
                message.chat.id,
                "💾 Черновик сохранён!\n\nВы можете продолжить заполнение позже из раздела «Черновики» в профиле.",
                reply_markup=create_main_menu()
            )
        except Exception as e:
            logger.error(f"Error saving draft (reply flow): {e}")
            bot.send_message(message.chat.id, "❌ Ошибка сохранения черновика. Попробуйте позже.")
            bot.register_next_step_handler(message, process_preview_confirmation)
    elif message.text == "✏️ Нет, изменить данные":
        # Предлагаем выбрать что изменить
        ask_what_to_edit(message, user_data)
    elif message.text == "❌ Отменить создание":
        cancel_distribution(message)
    elif message.text == "◀️ Назад в меню":
        # Заход из черновиков — сохраняем текущие данные в черновик и возврат в меню
        uid = message.from_user.id
        current = bot.user_data.get(uid, {})
        save_draft_to_db(uid, current)
        bot.user_data.pop(uid, None)
        bot.send_message(message.chat.id, "Возврат в меню.", reply_markup=create_main_menu())
    else:
        bot.send_message(message.chat.id, "Пожалуйста, выберите вариант из меню.")
        bot.register_next_step_handler(message, process_preview_confirmation)

def save_draft_to_db(user_id, user_data):
    """Обновить черновик в БД, если user_data пришёл из черновика (есть draft_id)."""
    draft_id = user_data.get("draft_id") if user_data else None
    if draft_id is None:
        return
    try:
        save_user_draft(user_id, "distribution_legacy", user_data, int(user_data.get("current_step") or 0), draft_id=draft_id)
    except Exception as e:
        logger.error(f"Error saving draft to DB: {e}")

EDIT_FIELD_CONFIG = {
    "Исполнитель": ("artist_name", "🎤 Введите нового исполнителя (-ей):", "text"),
    "Название релиза": ("release_name", "💿 Введите новое название релиза:", "text"),
    "Продюсер": ("producer", "🎹 Введите продюсера/битмейкера:", "text"),
    "Жанр": ("genre", "🎶 Введите жанр:", "text"),
    "Дата релиза": ("release_date", "📅 Введите дату релиза (ДД.ММ.ГГГГ):", "text"),
    "ФИО Исполнителя": ("performer_name", "👤 Введите ФИО исполнителя:", "text"),
    "Автор музыки": ("music_author", "✍️ Введите автора музыки:", "text"),
    "Обложка": ("cover", "🖼 Загрузите новую обложку (фото):", "photo"),
    "Аудиофайл": ("audio", "🎵 Загрузите новый аудиофайл:", "audio"),
    "Договор": ("contract", "📄 Загрузите новый договор (документ):", "document"),
    "Видеошот": ("videoshot_url", "🎥 Введите ссылку на видеошот или «нет»:", "text"),
    "Начало превью": ("preview_start", "⏱ Введите секунду начала превью (например 90):", "text"),
}

EDIT_FIELD_YES_NO = {
    "Эксплисит контент": "explicit_content",
    "Яндекс 'Скоро'": "yandex_soon",
    "Создать ссылки": "create_links",
    "TikTok коммерч.": "tiktok_commercial",
    "TikTok полная версия": "tiktok_full_version",
}

def _prompt_edit_one_field_and_register(message, user_data, prompt_text, field_key, value_type, reply_markup=None):
    """Отправить запрос нового значения и зарегистрировать обработчик — после ответа сохранить поле и показать превью."""
    msg = bot.send_message(
        message.chat.id,
        prompt_text,
        reply_markup=reply_markup or create_cancel_keyboard()
    )
    bot.register_next_step_handler(
        msg,
        lambda m: process_edit_one_value(m, user_data, field_key, value_type)
    )

def process_edit_one_value(message, user_data, field_key, value_type):
    """Сохранить новое значение одного поля и сразу показать превью (без цепочки шагов)."""
    user_id = message.from_user.id
    if is_cancel_message(message):
        return cancel_distribution(message)

    try:
        if value_type == "text":
            user_data[field_key] = (message.text or "").strip()
        elif value_type == "photo":
            if message.photo:
                user_data["cover_file_id"] = message.photo[-1].file_id
                user_data["cover_file_type"] = "photo"
            else:
                bot.send_message(message.chat.id, "Отправьте фото обложки.")
                _prompt_edit_one_field_and_register(message, user_data, "🖼 Загрузите обложку (фото):", field_key, value_type)
                return
        elif value_type == "audio":
            if message.audio:
                user_data["audio_file_id"] = message.audio.file_id
            elif message.document:
                user_data["audio_file_id"] = message.document.file_id
            else:
                bot.send_message(message.chat.id, "Отправьте аудио или документ.")
                _prompt_edit_one_field_and_register(message, user_data, "🎵 Загрузите аудиофайл:", field_key, value_type)
                return
        elif value_type == "document":
            if message.document:
                user_data["contract_file_id"] = message.document.file_id
            else:
                bot.send_message(message.chat.id, "Отправьте документ.")
                _prompt_edit_one_field_and_register(message, user_data, "📄 Загрузите договор (документ):", field_key, value_type)
                return
        elif value_type == "yes_no":
            user_data[field_key] = (message.text or "").strip().lower() == "да"
        else:
            user_data[field_key] = (message.text or "").strip()
    except Exception as e:
        logger.error(f"Error saving edit: {e}")
        bot.send_message(message.chat.id, "Ошибка сохранения. Попробуйте снова.")
        ask_what_to_edit(message, user_data)
        return

    bot.user_data[user_id] = user_data
    save_draft_to_db(user_id, user_data)
    show_release_preview(message, user_data, from_draft=user_data.get("from_draft", False))

RELEASE_TYPES = ("Single", "Maxi Single", "EP", "ALBUM")

def process_edit_release_type(message, user_data):
    """Обработка смены типа релиза: выбор из кнопок, сброс несовместимых полей, превью."""
    user_id = message.from_user.id
    if is_cancel_message(message):
        return cancel_distribution(message)
    if message.text == "◀️ Назад в меню":
        save_draft_to_db(user_id, user_data)
        bot.user_data.pop(user_id, None)
        bot.send_message(message.chat.id, "Возврат в меню.", reply_markup=create_main_menu())
        return

    if message.text not in RELEASE_TYPES:
        bot.send_message(message.chat.id, "Выберите тип релиза кнопкой ниже.")
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for t in RELEASE_TYPES:
            markup.add(t)
        markup.add("◀️ Назад в меню" if user_data.get("from_draft") else "❌ Отмена")
        bot.register_next_step_handler(message, lambda m: process_edit_release_type(m, user_data))
        return

    new_type = message.text
    old_type = user_data.get("release_type")

    user_data["release_type"] = new_type

    # При смене типа сбрасываем поля, которые не подходят новому типу (чтобы логика была корректной)
    if new_type == "ALBUM":
        # Было Single/EP/Maxi — очищаем сингловые поля, альбомные заполнятся заново
        for key in ("artist_name", "release_name", "producer", "genre", "cover_file_id", "audio_file_id",
                    "contract_file_id", "videoshot_url", "explicit_content", "preview_start", "yandex_soon",
                    "create_links", "tiktok_commercial", "tiktok_full_version", "performer_name", "music_author"):
            user_data.pop(key, None)
        user_data.setdefault("album_artist", "")
        user_data.setdefault("album_name", "")
        user_data.setdefault("tracks", [])
    else:
        # Было ALBUM или другой — очищаем альбомные поля
        for key in ("album_artist", "album_name", "tracks", "track_count", "current_track"):
            user_data.pop(key, None)
        user_data.setdefault("artist_name", user_data.get("artist_name", ""))
        user_data.setdefault("release_name", user_data.get("release_name", ""))

    bot.user_data[user_id] = user_data
    save_draft_to_db(user_id, user_data)
    show_release_preview(message, user_data, from_draft=user_data.get("from_draft", False))

def ask_what_to_edit(message, user_data):
    """Спрашивает пользователя, какие данные он хочет изменить"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    if user_data.get('release_type') == 'ALBUM':
        # Для альбома
        items = [
            "Исполнитель альбома", "Название альбома", "Дата релиза",
            "ФИО Исполнителя", "Автор музыки", "Трек-лист", "Обложка"
        ]
    else:
        # Для сингла
        items = [
            "Тип релиза", "Исполнитель", "Название релиза", "Продюсер",
            "Жанр", "Дата релиза", "ФИО Исполнителя", "Автор музыки",
            "Обложка", "Аудиофайл", "Договор", "Видеошот", "Эксплисит контент",
            "Начало превью", "Яндекс 'Скоро'", "Создать ссылки", "TikTok коммерч.", "TikTok полная версия"
        ]

    for item in items:
        markup.add(item)
    markup.add("◀️ Назад в меню" if user_data.get('from_draft') else "❌ Отменить создание")

    bot.send_message(
        message.chat.id,
        "Что вы хотите изменить?",
        reply_markup=markup
    )
    bot.register_next_step_handler(message, lambda msg: process_edit_choice(msg, user_data))

def process_edit_choice(message, user_data):
    """Обрабатывает выбор данных для редактирования"""
    choice = message.text
    user_id = message.from_user.id

    if choice == "❌ Отменить создание":
        return cancel_distribution(message)
    if choice == "◀️ Назад в меню":
        save_draft_to_db(user_id, user_data)
        bot.user_data.pop(user_id, None)
        bot.send_message(message.chat.id, "Возврат в меню.", reply_markup=create_main_menu())
        return

    # Сохраняем текущие данные
    bot.user_data[user_id] = user_data

    # Тип релиза — отдельно: сообщение «Выберите тип релиза» и кнопки Single, Maxi Single, EP, ALBUM
    if choice == "Тип релиза":
        markup_rt = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup_rt.add("Single", "Maxi Single", "EP", "ALBUM")
        markup_rt.add("◀️ Назад в меню" if user_data.get("from_draft") else "❌ Отмена")
        bot.send_message(message.chat.id, "Выберите тип релиза:", reply_markup=markup_rt)
        bot.register_next_step_handler(message, lambda m: process_edit_release_type(m, user_data))
        return

    # Редактирование одного поля: один запрос → сохранить → сразу превью (без цепочки шагов)
    if choice in EDIT_FIELD_CONFIG:
        field_key, prompt_text, value_type = EDIT_FIELD_CONFIG[choice]
        _prompt_edit_one_field_and_register(message, user_data, prompt_text, field_key, value_type)
        return
    if choice in EDIT_FIELD_YES_NO:
        field_key = EDIT_FIELD_YES_NO[choice]
        markup_yn = create_options_keyboard(["Да", "Нет"])
        msg = bot.send_message(
            message.chat.id,
            f"Новое значение для «{choice}»:",
            reply_markup=markup_yn
        )
        bot.register_next_step_handler(msg, lambda m: process_edit_one_value(m, user_data, field_key, "yes_no"))
        return

    # Сложные/альбомные поля — оставляем старый поток
    if choice == "Тип релиза":
        ask_release_type(message)
    elif choice == "Исполнитель":
        ask_artist_name(message)
    elif choice == "Название релиза":
        ask_release_name(message)
    elif choice == "Продюсер":
        ask_producer(message)
    elif choice == "Жанр":
        ask_genre(message)
    elif choice == "Дата релиза":
        ask_release_date(message)
    elif choice == "ФИО Исполнителя":
        ask_performer_name(message)
    elif choice == "Автор музыки":
        ask_music_author(message)
    elif choice == "Обложка":
        if user_data.get('release_type') == 'ALBUM':
            ask_album_cover(message)
        else:
            ask_cover(message)
    elif choice == "Аудиофайл":
        if user_data.get('release_type') == 'ALBUM':
            bot.user_data[user_id]['current_track'] = 1
            ask_track_audio(message)
        else:
            ask_audio(message)
    elif choice == "Договор":
        ask_contract(message)
    elif choice == "Видеошот":
        ask_videoshot(message)
    elif choice == "Эксплисит контент":
        markup = create_options_keyboard(["Да", "Нет"])
        msg = bot.send_message(
            message.chat.id,
            "14) Нецензурная лексика в треке (маты):",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_explicit_response)
    elif choice == "Начало превью":
        ask_preview_start(message)
    elif choice == "Яндекс 'Скоро'":
        markup = create_options_keyboard(["Да", "Нет"])
        msg = bot.send_message(
            message.chat.id,
            "17) Плашка 'скоро новый релиз' на Яндекс.Музыке:",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, ask_create_links)
    elif choice == "Создать ссылки":
        markup = create_options_keyboard(["Да", "Нет"])
        msg = bot.send_message(
            message.chat.id,
            "18) Сделать ссылку на все площадки?",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, ask_tiktok_features)
    elif choice == "TikTok коммерч.":
        markup = create_options_keyboard(["Да", "Нет"])
        msg = bot.send_message(
            message.chat.id,
            "19) Разрешить коммерческое использование в TikTok?",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_tiktok_commercial)
    elif choice == "TikTok полная версия":
        markup = create_options_keyboard(["Да", "Нет"])
        msg = bot.send_message(
            message.chat.id,
            "20) Разрешить полную версию трека в TikTok?",
            reply_markup=markup
        )
        bot.register_next_step_handler(msg, process_tiktok_full_version)
    elif choice == "Трек-лист":
        bot.send_message(message.chat.id, "Начинаем редактирование треков...")
        bot.user_data[user_id]['current_track'] = 1
        ask_track_info(message)
    elif choice == "Исполнитель альбома":
        bot.send_message(
            message.chat.id,
            "5) Исполнитель(-и) альбома:",
            reply_markup=create_cancel_keyboard()
        )
        bot.register_next_step_handler(message, process_album_artist)
    elif choice == "Название альбома":
        bot.send_message(
            message.chat.id,
            "4) Название альбома:",
            reply_markup=create_cancel_keyboard()
        )
        bot.register_next_step_handler(message, process_album_name)
    else:
        bot.send_message(message.chat.id, "Неверный выбор. Пожалуйста, попробуйте снова.")
        ask_what_to_edit(message, user_data)

def handle_distribution_agree(call):
    """Handle agreement with distribution terms"""
    conn = None
    try:
        conn = get_pg_connection()
        if not conn:
            bot.answer_callback_query(call.id, "Ошибка подключения к базе данных", show_alert=True)
            return

        with conn.cursor() as cursor:
            cursor.execute(
                'INSERT INTO distribution_agreements (user_id, agreed) VALUES (%s, %s)',
                (call.from_user.id, True)
            )
            conn.commit()

        ask_release_type(call.message)
    except Exception as e:
        logger.error(f"Error saving distribution agreement: {e}")
        bot.answer_callback_query(call.id, f"Ошибка: {str(e)}", show_alert=True)
    finally:
        if conn:
            return_pg_connection(conn)

def save_release_data(message):
    user_id = message.from_user.id
    user_data = bot.user_data.get(user_id, {})
    release_type = user_data.get('release_type', '')

    # Отладочная информация
    logger.info(f"Saving release data for user {user_id}, release_type: {release_type}")
    logger.info(f"User data cover_file_id: {user_data.get('cover_file_id')}")
    logger.info(f"Full user_data keys: {list(user_data.keys())}")
    debug_user_data(user_id, "before_save_release_data")

    conn = get_pg_connection()
    if not conn:
        bot.send_message(message.chat.id, "❌ Ошибка подключения к БД")
        return

    try:
        cursor = conn.cursor()

        if release_type == "ALBUM" or release_type == "EP" or release_type == "Maxi Single":
            # Сохранение альбома
            # Используем контракт первого трека для записи альбома
            first_track_contract = (user_data.get('tracks') or [{}])[0].get('contract_file_id', 'N/A')
            cursor.execute('''
                INSERT INTO releases (
                    user_id, release_type, artist_name, release_name,
                    genre, cover_file_id, release_date, performer_name,
                    music_author, contract_file_id, videoshot_url, explicit_content,
                    lyrics_file_id, preview_start, yandex_soon, create_links,
                    tiktok_commercial, tiktok_full_version, status, is_album
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                user_id,
                "ALBUM",
                user_data.get('album_artist') or user_data.get('artist_name'),
                user_data.get('album_name') or user_data.get('release_name'),
                (user_data.get('tracks') or [{}])[0].get('genre') or 'N/A',
                user_data.get('cover_file_id'),
                user_data.get('release_date'),
                user_data.get('performer_name'),
                user_data.get('music_author'),
                first_track_contract,
                user_data.get('videoshot_url'),
                user_data.get('explicit_content', False),
                user_data.get('lyrics_file_id'),
                user_data.get('preview_start'),
                user_data.get('yandex_soon', False),
                user_data.get('create_links', False),
                user_data.get('tiktok_commercial', False),
                user_data.get('tiktok_full_version', False),
                'pending',
                True
            ))
            album_id = cursor.fetchone()[0]

            # Сохранение треков
            for track in user_data.get('tracks', []):
                cursor.execute('''
                    INSERT INTO releases (
                        user_id, release_type, artist_name, release_name, producer, genre,
                        audio_file_id, release_date, performer_name, music_author,
                        contract_file_id, explicit_content, status, album_id, is_track, track_number,
                        lyrics_file_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (
                    user_id,
                    "TRACK",
                    user_data.get('album_artist') or user_data.get('artist_name'),
                    track.get('track_name'),
                    track.get('producer'),
                    track.get('genre') or 'N/A',
                    track.get('audio_file_id'),
                    user_data.get('release_date'),
                    user_data.get('performer_name'),
                    user_data.get('music_author'),
                    track.get('contract_file_id'),
                    user_data.get('explicit_content', False),
                    'pending',
                    album_id,
                    True,
                    track.get('track_number'),
                    track.get('lyrics_file_id')
                ))

            release_name = user_data.get('album_name') or user_data.get('release_name') or 'Релиз'

        else:
            # Сохранение сингла
            cursor.execute('''
                INSERT INTO releases (
                    user_id, release_type, artist_name, release_name, producer, genre,
                    cover_file_id, audio_file_id, release_date, performer_name,
                    music_author, contract_file_id, videoshot_url, explicit_content,
                    lyrics_file_id, preview_start, yandex_soon, create_links,
                    tiktok_commercial, tiktok_full_version, status, is_album
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (
                user_id,
                user_data.get('release_type'),
                user_data.get('artist_name'),
                user_data.get('release_name'),
                user_data.get('producer'),
                user_data.get('genre') or 'N/A',
                user_data.get('cover_file_id'),
                user_data.get('audio_file_id'),
                user_data.get('release_date'),
                user_data.get('performer_name'),
                user_data.get('music_author'),
                user_data.get('contract_file_id'),
                user_data.get('videoshot_url'),
                user_data.get('explicit_content', False),
                user_data.get('lyrics_file_id'),
                user_data.get('preview_start'),
                user_data.get('yandex_soon', False),
                user_data.get('create_links', False),
                user_data.get('tiktok_commercial', False),
                user_data.get('tiktok_full_version', False),
                'pending',
                False  # not album
            ))
            release_id = cursor.fetchone()[0]
            release_name = user_data['release_name']

        conn.commit()

        # Уведомление пользователя
        bot.send_message(
            message.chat.id,
            f"✅ Релиз «{release_name}» успешно отправлен на модерацию!",
            reply_markup=create_main_menu()
        )

        # Уведомление админов
        notify_admins_about_new_release(user_id, release_id if release_type != "ALBUM" else album_id)

    except Exception as e:
        logger.exception(f"Ошибка сохранения релиза")
        bot.send_message(
            message.chat.id,
            f"❌ Критическая ошибка: {str(e)}",
            reply_markup=create_main_menu()
        )
    finally:
        if user_id in bot.user_data:
            del bot.user_data[user_id]
        if conn:
            cursor.close()
            return_pg_connection(conn)

class DistributionForm:
    def __init__(self):
        self.data = {}
        self.current_field = None
        self.message_id = None  # ID сообщения для редактирования
        self.chat_id = None  # ID чата
        self.fields = [
            ("track_name", "Название трека:"),
            ("artist_name", "Имя артиста (как должно отображаться на площадках):"),
            ("release_date", "Дата релиза (ДД.ММ.ГГГГ):"),
            ("featuring", "Featuring артисты (если есть, иначе напишите 'нет'):"),
            ("explicit", "Есть ли нецензурная лексика? (да/нет):"),
            ("genre", "Жанр музыки:"),
            ("lyrics", "Текст песни:")
        ]
        # Режим запуска админом от имени другого пользователя
        self.started_by_admin = False
        self.target_user_id = None

def show_distribution_question(chat_id, message_id, form):
    """Show distribution question with navigation buttons"""
    field_name, question = form.fields[form.current_field]

    # Показываем текущий ответ, если он есть
    current_answer = form.data.get(field_name, "")
    if current_answer:
        text = f"📝 {question}\n\n✅ Ваш ответ: {current_answer}"
    else:
        text = f"📝 {question}\n\n💬 Введите ваш ответ:"

    # Показываем прогресс
    progress = f"\n\n📊 Вопрос {form.current_field + 1} из {len(form.fields)}"
    text += progress

    # Создаем клавиатуру с кнопками
    markup = types.InlineKeyboardMarkup(row_width=2)

    buttons_row = []

    # Кнопка "Назад" - доступна если не первый вопрос
    if form.current_field > 0:
        buttons_row.append(types.InlineKeyboardButton("◀️ Назад", callback_data="distribution_prev"))

    # Кнопка "Вперед" - доступна только если есть ответ на текущий вопрос
    if current_answer and form.current_field < len(form.fields) - 1:
        buttons_row.append(types.InlineKeyboardButton("Вперед ▶️", callback_data="distribution_next"))

    if buttons_row:
        markup.add(*buttons_row)

    # Кнопка "Изменить информацию" - доступна если есть ответ
    if current_answer:
        markup.add(types.InlineKeyboardButton("✏️ Изменить информацию", callback_data="distribution_edit"))

    # Если это последний вопрос и есть ответ, показываем кнопку завершения
    if form.current_field == len(form.fields) - 1 and current_answer:
        markup.add(types.InlineKeyboardButton("✅ Завершить заполнение", callback_data="distribution_complete"))

    try:
        bot.edit_message_text(
            text,
            chat_id,
            message_id,
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Error editing message: {e}")

def start_distribution_form(call):
    """Start distribution form"""
    user_id = call.from_user.id
    bot.distribution_forms = getattr(bot, 'distribution_forms', {})
    bot.distribution_forms[user_id] = DistributionForm()

    # Start with first field
    form = bot.distribution_forms[user_id]
    form.current_field = 0
    form.message_id = call.message.message_id
    form.chat_id = call.message.chat.id

    show_distribution_question(call.message.chat.id, call.message.message_id, form)
    bot.register_next_step_handler(call.message, process_distribution_form)

def process_distribution_form(message):
    """Process distribution form answers"""
    user_id = message.from_user.id
    if user_id not in bot.distribution_forms:
        return

    form = bot.distribution_forms[user_id]
    field_name, _ = form.fields[form.current_field]
    form.data[field_name] = message.text

    # Если это не последний вопрос, автоматически переходим к следующему
    if form.current_field < len(form.fields) - 1:
        form.current_field += 1
        # Показываем следующий вопрос с кнопками (обновляем сообщение)
        show_distribution_question(form.chat_id, form.message_id, form)
        # Регистрируем обработчик для следующего ответа
        bot.register_next_step_handler(message, process_distribution_form)
    else:
        # Это последний вопрос - показываем его с кнопкой завершения
        show_distribution_question(form.chat_id, form.message_id, form)

def complete_distribution_form(chat_id, message_id, form, user_id):
    """Complete distribution form and proceed to payment"""
    # Format collected data
    summary = (
        "📝 Проверьте введенные данные:\n\n"
        f"🎵 Название: {form.data.get('track_name', 'Не указано')}\n"
        f"👤 Артист: {form.data.get('artist_name', 'Не указано')}\n"
        f"📅 Дата релиза: {form.data.get('release_date', 'Не указано')}\n"
        f"👥 Featuring: {form.data.get('featuring', 'Не указано')}\n"
        f"🔞 Explicit: {form.data.get('explicit', 'Не указано')}\n"
        f"🎼 Жанр: {form.data.get('genre', 'Не указано')}\n"
        f"📜 Текст: {form.data.get('lyrics', 'Не указано')[:100]}...\n\n"
        "💰 Стоимость: 1299₽"
    )
    # Старая логика админских действий удалена - теперь используется обычный процесс дистрибуции
    # Проверяем, создается ли релиз за артиста
    creating_for_artist = (is_admin(user_id) and
                          hasattr(bot, 'admin_release_target') and
                          bot.admin_release_target.get(user_id))

    if creating_for_artist:
        target_user_id = bot.admin_release_target[user_id]
        summary += f"\n\n🎭 Создается для пользователя ID: {target_user_id}"

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("💳 Оплатить", callback_data="pay_distribution"),
        types.InlineKeyboardButton("🔄 Начать заново", callback_data="distribution_start"),
        types.InlineKeyboardButton("◀️ Отмена", callback_data="services_back")
    )

    try:
        bot.edit_message_text(
            summary,
            chat_id,
            message_id,
            reply_markup=markup
        )
    except Exception as e:
        logger.error(f"Error editing message in complete_distribution_form: {e}")
        # Если не удалось отредактировать, отправляем новое сообщение
        bot.send_message(chat_id, summary, reply_markup=markup)

def handle_distribution_prev(call):
    """Handle previous question button"""
    user_id = call.from_user.id
    if user_id not in bot.distribution_forms:
        bot.answer_callback_query(call.id, "❌ Форма не найдена. Начните заново.")
        return

    form = bot.distribution_forms[user_id]
    if form.current_field > 0:
        form.current_field -= 1
        show_distribution_question(call.message.chat.id, call.message.message_id, form)
        bot.answer_callback_query(call.id)
    else:
        bot.answer_callback_query(call.id, "Это первый вопрос", show_alert=True)

def handle_distribution_next(call):
    """Handle next question button"""
    user_id = call.from_user.id
    if user_id not in bot.distribution_forms:
        bot.answer_callback_query(call.id, "❌ Форма не найдена. Начните заново.")
        return

    form = bot.distribution_forms[user_id]
    field_name, _ = form.fields[form.current_field]

    # Проверяем, что есть ответ на текущий вопрос
    if not form.data.get(field_name):
        bot.answer_callback_query(call.id, "❌ Сначала ответьте на текущий вопрос", show_alert=True)
        return

    if form.current_field < len(form.fields) - 1:
        form.current_field += 1
        show_distribution_question(call.message.chat.id, call.message.message_id, form)
        bot.answer_callback_query(call.id)
        # Регистрируем обработчик для следующего ответа
        bot.register_next_step_handler(call.message, process_distribution_form)
    else:
        bot.answer_callback_query(call.id, "Это последний вопрос", show_alert=True)

def handle_distribution_edit(call):
    """Handle edit information button"""
    user_id = call.from_user.id
    if user_id not in bot.distribution_forms:
        bot.answer_callback_query(call.id, "❌ Форма не найдена. Начните заново.")
        return

    form = bot.distribution_forms[user_id]
    field_name, _ = form.fields[form.current_field]

    # Очищаем текущий ответ
    form.data[field_name] = ""

    # Показываем вопрос без ответа
    show_distribution_question(call.message.chat.id, call.message.message_id, form)
    bot.answer_callback_query(call.id, "Введите новый ответ")

    # Регистрируем обработчик для нового ответа
    bot.register_next_step_handler(call.message, process_distribution_form)

def handle_distribution_complete(call):
    """Handle complete form button"""
    user_id = call.from_user.id
    if user_id not in bot.distribution_forms:
        bot.answer_callback_query(call.id, "❌ Форма не найдена. Начните заново.")
        return

    form = bot.distribution_forms[user_id]

    # Проверяем, что все поля заполнены
    all_filled = all(form.data.get(field_name) for field_name, _ in form.fields)
    if not all_filled:
        bot.answer_callback_query(call.id, "❌ Заполните все поля перед завершением", show_alert=True)
        return

    complete_distribution_form(call.message.chat.id, call.message.message_id, form, user_id)
    bot.answer_callback_query(call.id)

def handle_use_promo_distribution(call):
    """Показать список промокодов на скидку при оплате дистрибуции"""
    user_id = call.from_user.id
    base_amount = _distribution_base_price(bot.user_data.get(user_id, {}))
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к БД", show_alert=True)
        return
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT pc.id, pc.code, pc.discount
            FROM user_discount_promos udp
            JOIN promo_codes pc ON pc.id = udp.promo_code_id AND pc.is_active = TRUE
            WHERE udp.user_id = %s
            AND (pc.expires_at IS NULL OR pc.expires_at > CURRENT_TIMESTAMP)
        """, (user_id,))
        rows = cursor.fetchall()
        if not rows:
            bot.answer_callback_query(call.id, "Нет доступных промокодов. Введите промокод в «Мой профиль» → «Ввести промокод».", show_alert=True)
            return
        markup = types.InlineKeyboardMarkup(row_width=1)
        for promo_id, code, discount in rows:
            pct = float(discount or 0)
            markup.add(types.InlineKeyboardButton(f"🎟 {code} — скидка {pct:.0f}%", callback_data=f"apply_promo_dist_{promo_id}"))
        markup.add(types.InlineKeyboardButton("◀️ Без промокода", callback_data=f"distribution_pay_{base_amount}"))
        bot.edit_message_text(
            f"Выберите промокод на скидку (базовая сумма {base_amount}₽):",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        logger.error(f"Error listing discount promos: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка загрузки промокодов", show_alert=True)
    finally:
        if cursor:
            cursor.close()
        return_pg_connection(conn)

def handle_apply_promo_distribution(call):
    """Применить выбранный промокод на скидку и показать сумму к оплате"""
    try:
        promo_id = int(call.data.replace("apply_promo_dist_", ""))
    except ValueError:
        bot.answer_callback_query(call.id, "❌ Неверные данные", show_alert=True)
        return
    user_id = call.from_user.id
    base_amount = _distribution_base_price(bot.user_data.get(user_id, {}))
    conn = get_pg_connection()
    if not conn:
        bot.answer_callback_query(call.id, "❌ Ошибка подключения к БД", show_alert=True)
        return
    cursor = None
    try:
        cursor = conn.cursor()
        row = _owned_discount_promo(cursor, user_id, promo_id)
        if not row:
            bot.answer_callback_query(call.id, "Промокод недоступен", show_alert=True)
            return
        code, discount_pct = row[0], float(row[1])
        discounted = _discounted_amount(base_amount, discount_pct)
        bot.user_data.setdefault(user_id, {})['distribution_promo_id'] = promo_id
        bot.user_data.setdefault(user_id, {})['distribution_discount_pct'] = discount_pct
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"Подтвердить оплату {discounted}₽ (скидка {discount_pct:.0f}%)", callback_data=f"distribution_pay_{discounted}"))
        bot.edit_message_text(
            f"Применён промокод {code}: скидка {discount_pct:.0f}%.\nСумма к оплате: {discounted}₽ (было {base_amount}₽).",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        bot.answer_callback_query(call.id)
    except Exception as e:
        logger.error(f"Error applying promo: {e}")
        bot.answer_callback_query(call.id, "❌ Ошибка применения промокода", show_alert=True)
    finally:
        if cursor:
            cursor.close()
        return_pg_connection(conn)
