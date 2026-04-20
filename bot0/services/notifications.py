"""Notification helpers shared by legacy and modular handlers."""
from __future__ import annotations

from datetime import datetime
from typing import Callable, Iterable

from telebot import types


def create_admin_notification_message(release_info, bot_token: str) -> str:
    """Create a detailed moderation message for admins."""
    fields = {
        "ID релиза": release_info[0],
        "Тип релиза": release_info[2],
        "Артист": f"{release_info[3]} (@{release_info[-1]})",
        "Название": release_info[4],
        "Продюсер": release_info[5] or "не указан",
        "Жанр": release_info[6],
        "Дата релиза": release_info[9].strftime("%d.%m.%Y"),
        "Исполнитель": release_info[10],
        "Автор музыки": release_info[11],
        "Эксплисит контент": "да" if release_info[14] else "нет",
        "Превью (сек)": release_info[16] or "не указано",
        'Яндекс "Скоро"': "да" if release_info[17] else "нет",
        "Создать ссылки": "да" if release_info[18] else "нет",
        "TikTok коммерч.": "да" if release_info[19] else "нет",
        "TikTok полная версия": "да" if release_info[20] else "нет",
    }

    message = "🎵 *Новый релиз на модерацию!*\n\n"
    message += "\n".join([f"*{key}:* {value}" for key, value in fields.items()])

    if release_info[7]:
        message += f"\n\n🎨 [Обложка](https://api.telegram.org/file/bot{bot_token}/{release_info[7]})"
    if release_info[8]:
        message += f"\n🎧 [Аудио](https://api.telegram.org/file/bot{bot_token}/{release_info[8]})"
    if release_info[12]:
        message += f"\n📄 [Контракт](https://api.telegram.org/file/bot{bot_token}/{release_info[12]})"

    return message


def notify_all_admins(bot, admin_ids: Iterable[int], message_text: str, logger) -> None:
    sent_any = False
    for admin_id in admin_ids:
        try:
            bot.send_message(
                admin_id,
                message_text,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
            sent_any = True
            logger.info("Уведомление отправлено админу %s", admin_id)
        except Exception as exc:
            logger.error("Не удалось уведомить админа %s: %s", admin_id, exc)

    if not sent_any:
        logger.warning("Не найдено ни одного администратора для уведомления")


def notify_release_admins(
    bot,
    user_id: int,
    release_id: int,
    get_connection: Callable,
    return_connection: Callable,
    get_admin_ids: Callable[[], list[int]],
    logger,
    escape_markdown: Callable[[object], str],
) -> None:
    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        cursor.execute("SELECT name, tg FROM label WHERE telegram_id = %s", (user_id,))
        user_info = cursor.fetchone()
        cursor.execute(
            """
            SELECT artist_name, release_name, release_date
            FROM releases WHERE id = %s
            """,
            (release_id,),
        )
        release_info = cursor.fetchone()

        if not (user_info and release_info):
            return

        artist_name, username = user_info
        _release_artist, release_name, release_date = release_info
        message = (
            "🎵 Новый релиз на проверку!\n\n"
            f"Артист: {escape_markdown(artist_name)} (@{escape_markdown(username)})\n"
            f"Название: {escape_markdown(release_name)}\n"
            f"Дата релиза: {release_date.strftime('%d.%m.%Y')}\n"
            f"ID: {release_id}"
        )

        for admin_id in get_admin_ids():
            try:
                bot.send_message(admin_id, message)
            except Exception as exc:
                logger.error("Failed to notify admin %s: %s", admin_id, exc)
    except Exception as exc:
        logger.error("Error in admin notification: %s", exc)
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_connection(conn)


def notify_admins_about_new_release(
    bot,
    user_id: int,
    release_id: int,
    get_connection: Callable,
    return_connection: Callable,
    logger,
) -> None:
    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            logger.error("Database connection failed for admin notification")
            return

        cursor = conn.cursor()
        cursor.execute("SELECT name, tg FROM label WHERE telegram_id = %s", (user_id,))
        user_info = cursor.fetchone()
        if not user_info:
            logger.error("User %s not found", user_id)
            return

        cursor.execute("SELECT release_name, release_date FROM releases WHERE id = %s", (release_id,))
        release_info = cursor.fetchone()
        if not release_info:
            logger.error("Release %s not found", release_id)
            return

        artist_name, username = user_info
        release_name, release_date = release_info
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📎 Просмотреть вложения", callback_data=f"admin_view_release_{release_id}"))

        message = (
            "📢 Новый релиз на проверку!\n\n"
            f"🎤 Артист: {artist_name} (@{username})\n"
            f"🎵 Название: {release_name}\n"
            f"📅 Дата релиза: {release_date.strftime('%d.%m.%Y')}\n"
            f"🆔 ID релиза: {release_id}"
        )

        cursor.execute("SELECT telegram_id FROM label WHERE admin = 1")
        for (admin_id,) in cursor.fetchall():
            try:
                bot.send_message(admin_id, message, reply_markup=markup)
            except Exception as exc:
                logger.error("Failed to notify admin %s: %s", admin_id, exc)
    except Exception as exc:
        logger.error("Error in admin notification: %s", exc)
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_connection(conn)


def notify_admins_about_report_request(
    bot,
    user_id: int,
    report_id: int,
    user_name: str,
    username: str,
    get_connection: Callable,
    return_connection: Callable,
    logger,
) -> None:
    message = (
        "📊 Новый запрос отчета!\n\n"
        f"👤 Пользователь: {user_name} (@{username})\n"
        f"🆔 ID пользователя: {user_id}\n"
        f"📊 ID запроса: {report_id}\n"
        f"📅 Дата запроса: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n"
        "💡 Перейдите в админ панель → Пользователи → Запросы отчетов для ответа"
    )

    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            return

        cursor = conn.cursor()
        cursor.execute("SELECT telegram_id FROM label WHERE admin = 1")
        for (admin_id,) in cursor.fetchall():
            try:
                bot.send_message(admin_id, message)
            except Exception as exc:
                logger.error("Failed to notify admin %s about report request: %s", admin_id, exc)
    except Exception as exc:
        logger.error("Error notifying admins about report request: %s", exc)
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_connection(conn)


def notify_order_admins(bot, message: str, get_connection: Callable, return_connection: Callable, logger) -> None:
    conn = None
    cursor = None
    try:
        conn = get_connection()
        if not conn:
            logger.error("Could not connect to database in notify_admins")
            return

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT telegram_id FROM label
            WHERE admin = 1 OR owner = 1 OR creator = 1
            """
        )
        for (user_id,) in cursor.fetchall():
            try:
                bot.send_message(user_id, message)
            except Exception as exc:
                logger.error("Failed to send notification to user %s: %s", user_id, exc)
    except Exception as exc:
        logger.error("PostgreSQL error in notify_admins: %s", exc)
    finally:
        if cursor:
            cursor.close()
        if conn:
            return_connection(conn)
