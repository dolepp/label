"""Admin flow for creating a release on behalf of an artist."""
from __future__ import annotations

import logging
from typing import Any, Callable

from telebot import types

logger = logging.getLogger(__name__)

bot = None
is_admin: Callable[[int], bool] | None = None
get_pg_connection: Callable[..., Any] | None = None
return_pg_connection: Callable[[Any], None] | None = None
save_release_data_for_user: Callable[[int, int], None] | None = None


def configure(**context: Any) -> None:
    globals().update({key: value for key, value in context.items() if value is not None})


def _require(name: str) -> Any:
    value = globals().get(name)
    if value is None:
        raise RuntimeError(f"artist-release service dependency is not configured: {name}")
    return value


def handle_service_release_for_artist(call):
    active_bot = _require("bot")
    if not _require("is_admin")(call.from_user.id):
        active_bot.answer_callback_query(call.id, "❌ Эта функция доступна только администраторам", show_alert=True)
        return

    active_bot.edit_message_text(
        "📤 Выгрузка релиза за артиста\n\n"
        "Введите Telegram ID пользователя, для которого нужно создать релиз:\n\n"
        "💡 Можно найти ID пользователя в админ-панели → Пользователи",
        call.message.chat.id,
        call.message.message_id,
    )
    active_bot.register_next_step_handler(call.message, process_artist_user_id)


def process_artist_user_id(message):
    active_bot = _require("bot")
    if not _require("is_admin")(message.from_user.id):
        active_bot.reply_to(message, "❌ Недостаточно прав")
        return

    try:
        target_user_id = int(message.text.strip())
        conn = _require("get_pg_connection")()
        if not conn:
            active_bot.reply_to(message, "❌ Ошибка подключения к базе данных")
            return

        cursor = None
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT tg FROM label WHERE telegram_id = %s", (target_user_id,))
            user_result = cursor.fetchone()
        finally:
            if cursor:
                cursor.close()
            _require("return_pg_connection")(conn)

        if not user_result:
            active_bot.reply_to(message, f"❌ Пользователь с ID {target_user_id} не найден в базе данных")
            return

        username = user_result[0] or f"ID_{target_user_id}"
        active_bot.admin_release_target = getattr(active_bot, "admin_release_target", {})
        active_bot.admin_release_target[message.from_user.id] = target_user_id

        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Начать создание релиза", callback_data="service_distribution"),
            types.InlineKeyboardButton("◀️ Назад к услугам", callback_data="services_back"),
        )
        active_bot.reply_to(
            message,
            f"✅ Выбран пользователь: {username} (ID: {target_user_id})\n\n"
            "Теперь вы будете проходить обычный процесс дистрибуции, "
            "но релиз будет создан от имени этого пользователя.",
            reply_markup=markup,
        )
        modify_distribution_for_artist_release(message.from_user.id, target_user_id)
    except ValueError:
        active_bot.reply_to(message, "❌ Неверный формат ID. Введите числовой Telegram ID:")
        active_bot.register_next_step_handler(message, process_artist_user_id)
    except Exception as exc:
        logger.error("Error processing artist user ID: %s", exc)
        active_bot.reply_to(message, "❌ Произошла ошибка при обработке")


def modify_distribution_for_artist_release(admin_id: int, target_user_id: int):
    """Install compatibility save hook for legacy admin-on-behalf flow."""
    active_bot = _require("bot")
    original_save = getattr(active_bot, "original_save_release_data_for_user", None)
    if original_save is None:
        original_save = _require("save_release_data_for_user")
        active_bot.original_save_release_data_for_user = original_save

    def custom_save_release_data_for_user(user_id: int, chat_id: int) -> None:
        if user_id != admin_id or not getattr(active_bot, "admin_release_target", {}).get(admin_id):
            active_bot.original_save_release_data_for_user(user_id, chat_id)
            return

        actual_user_id = active_bot.admin_release_target[admin_id]
        logger.info("Admin %s creating release for user %s", admin_id, actual_user_id)
        user_data = getattr(active_bot, "user_data", {}).get(admin_id, {})
        release_type = user_data.get("release_type", "")

        if release_type != "Single":
            active_bot.original_save_release_data_for_user(actual_user_id, chat_id)
            return

        conn = _require("get_pg_connection")()
        if not conn:
            active_bot.send_message(chat_id, "❌ Ошибка подключения к БД")
            return

        cursor = None
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO releases (
                    user_id, release_type, artist_name, release_name, producer,
                    genre, cover_file_id, audio_file_id, release_date, performer_name,
                    music_author, contract_file_id, videoshot_url, explicit_content,
                    lyrics_file_id, preview_start, yandex_soon, create_links,
                    tiktok_commercial, tiktok_full_version, status
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    actual_user_id,
                    "Single",
                    user_data.get("artist_name"),
                    user_data.get("release_name"),
                    user_data.get("producer"),
                    user_data.get("genre") or "N/A",
                    user_data.get("cover_file_id"),
                    user_data.get("audio_file_id"),
                    user_data.get("release_date"),
                    user_data.get("performer_name"),
                    user_data.get("music_author"),
                    user_data.get("contract_file_id"),
                    user_data.get("videoshot_url"),
                    user_data.get("explicit_content", False),
                    user_data.get("lyrics_file_id"),
                    user_data.get("preview_start"),
                    user_data.get("yandex_soon", False),
                    user_data.get("create_links", False),
                    user_data.get("tiktok_commercial", False),
                    user_data.get("tiktok_full_version", False),
                    "pending",
                ),
            )
            release_id = cursor.fetchone()[0]
            conn.commit()
            active_bot.send_message(chat_id, f"✅ Релиз #{release_id} создан за пользователя {actual_user_id}")
            try:
                active_bot.send_message(actual_user_id, "📀 Для вас создан релиз администратором. Проверьте раздел 'Мои релизы'.")
            except Exception:
                pass
            active_bot.admin_release_target.pop(admin_id, None)
        except Exception as exc:
            logger.error("Error creating release for artist: %s", exc)
            active_bot.send_message(chat_id, f"❌ Ошибка создания релиза: {str(exc)}")
        finally:
            if cursor:
                cursor.close()
            _require("return_pg_connection")(conn)

    globals()["save_release_data_for_user"] = custom_save_release_data_for_user
