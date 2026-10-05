"""Legacy and improved distribution routing moved out of the monolith.

This module owns Telegram handler registration. The old reply-keyboard
distribution step-chain lives in handlers.legacy_distribution_steps and is
wired through injected dependencies rather than importing label.py.
"""
from __future__ import annotations

import logging

from telebot import types

from db.repositories.drafts import get_user_draft, normalize_distribution_draft_data, save_user_draft
from handlers import legacy_distribution_steps as steps

logger = logging.getLogger(__name__)


def _legacy():
    # Temporary bridge for the non-distribution edit-release-name callback only.
    import label

    return label


def _ctx(name):
    value = getattr(steps, name, None)
    if value is None:
        raise RuntimeError(f"legacy distribution context is not configured: {name}")
    return value


class ImprovedDistributionForm:
    """Improved single-release distribution form with navigation."""

    def __init__(self, release_type="single"):
        self.release_type = release_type
        self.data = {}
        self.current_step = 0
        self.message_id = None
        self.chat_id = None
        self.user_id = None
        self.steps = [
            ("artist_name", "🎤 3) Исполнитель(-и)\n\nУкажите основного исполнителя или группу:", "text"),
            ("release_name", "💿 4) Название релиза\n\nВведите название сингла:", "text"),
            ("producer", "🎹 5) prod. by\n\nУкажите продюсера/битмейкера:", "text"),
            ("genre", "🎶 6) Жанр релиза\n\nУкажите музыкальный жанр:", "text"),
            ("cover", "🖼 7) Обложка релиза\n\nЗагрузите обложку (PNG/JPG 3000×3000):", "photo"),
            ("audio", "🎵 8) Файл трека\n\nЗагрузите аудиофайл (WAV, STEREO):", "audio"),
            ("release_date", "📅 9) Дата релиза\n\nВведите дату (ДД.ММ.ГГГГ):", "text"),
            ("performer_name", "👤 10) ФИО Исполнителя(-ей)\n\nУкажите полное имя:", "text"),
            ("music_author", "✍️ 11) ФИО Автора(-ов) музыки\n\nУкажите автора:", "text"),
            ("beat_contract", "📄 12) ДОГОВОР НА БИТ\n\nЗагрузите договор:", "document"),
            ("videoshot_url", "🎥 13) Ссылка на видеошот\n\nДля Яндекс.Музыки (если нет - напишите 'нет'):", "text"),
            ("explicit_content", "🔞 14) Нецензурная лексика\n\nЕсть маты в треке?", "yes_no"),
            ("lyrics_file", "📝 15) Текст трека\n\nЗагрузите файл txt:", "document"),
            ("preview_start", "⏱ 16) Начало предпрослушивания\n\nСекунда (например 90 = 1:30):", "text"),
            ("yandex_soon", "🎤 17) Плашка 'скоро'\n\nНа Яндекс.Музыке?", "yes_no"),
            ("platform_links", "🔗 18) Ссылки на все площадки\n\nСделать?", "yes_no"),
            ("tiktok_commercial", "🎵 19) TikTok коммерческое\n\nРазрешить?", "yes_no"),
            ("tiktok_full", "🎶 20) TikTok полная версия\n\nРазрешить?", "yes_no"),
        ]

    def get_current_step(self):
        return self.steps[self.current_step] if self.current_step < len(self.steps) else None

    def get_progress(self):
        return f"📊 Шаг {self.current_step + 1} из {len(self.steps)}"

    def has_answer(self, step_index=None):
        step_index = self.current_step if step_index is None else step_index
        if step_index >= len(self.steps):
            return False
        return bool(self.data.get(self.steps[step_index][0]))


def _forms(bot):
    if not hasattr(bot, "improved_distribution_forms"):
        bot.improved_distribution_forms = {}
    return bot.improved_distribution_forms


def _show_improved_distribution_step(bot, chat_id, message_id, form):
    step = form.get_current_step()
    if not step:
        _show_improved_distribution_preview(bot, chat_id, message_id, form)
        return
    field_name, question, field_type = step
    current_value = form.data.get(field_name, "")
    text = question + "\n\n" + form.get_progress()
    if current_value:
        if field_type in ["photo", "audio", "document"]:
            text += "\n\n✅ Файл загружен"
        else:
            value_display = current_value if len(str(current_value)) < 100 else str(current_value)[:100] + "..."
            text += f"\n\n✅ Ваш ответ: {value_display}"
    markup = types.InlineKeyboardMarkup(row_width=2)
    if field_type == "yes_no" and not current_value:
        markup.add(
            types.InlineKeyboardButton("✅ Да", callback_data=f"idist_yes_{field_name}"),
            types.InlineKeyboardButton("❌ Нет", callback_data=f"idist_no_{field_name}"),
        )
    nav_row = []
    if form.current_step > 0:
        nav_row.append(types.InlineKeyboardButton("◀️ Назад", callback_data="idist_prev"))
    if current_value and form.current_step < len(form.steps) - 1:
        nav_row.append(types.InlineKeyboardButton("▶️ Вперёд", callback_data="idist_next"))
    if nav_row:
        markup.add(*nav_row)
    action_row = []
    if current_value:
        action_row.append(types.InlineKeyboardButton("✏️ Изменить", callback_data="idist_edit"))
    action_row.append(types.InlineKeyboardButton("❌ Отменить всё", callback_data="idist_cancel_all"))
    markup.add(*action_row)
    if form.current_step == len(form.steps) - 1 and current_value:
        markup.add(types.InlineKeyboardButton("✅ Просмотр и оплата", callback_data="idist_preview"))
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    except Exception as exc:
        logger.error("Error editing distribution message: %s", exc)


def _show_improved_distribution_preview(bot, chat_id, message_id, form):
    text = "📝 ПРЕДВАРИТЕЛЬНЫЙ ПРОСМОТР РЕЛИЗА\n\n"
    text += f"🎤 Исполнитель: {form.data.get('artist_name', '-')}\n"
    text += f"💿 Название: {form.data.get('release_name', '-')}\n"
    text += f"🎹 Продюсер: {form.data.get('producer', '-')}\n"
    text += f"🎶 Жанр: {form.data.get('genre', '-')}\n"
    text += f"📅 Дата: {form.data.get('release_date', '-')}\n"
    text += f"🔞 Маты: {form.data.get('explicit_content', '-')}\n\n"
    is_artist = _is_artist(form.user_id)
    text += "🎉 БЕСПЛАТНО! У вас статус Artist" if is_artist else "💵 Стоимость: 1299₽"
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("✅ Отправить бесплатно", callback_data="idist_submit_free") if is_artist else types.InlineKeyboardButton("💳 Оплатить и отправить", callback_data="idist_pay"))
    markup.add(
        types.InlineKeyboardButton("💾 Сохранить как черновик", callback_data="idist_save_draft"),
        types.InlineKeyboardButton("✏️ Изменить данные", callback_data="idist_edit_back"),
        types.InlineKeyboardButton("❌ Отменить", callback_data="idist_cancel_all"),
    )
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
    except Exception as exc:
        logger.error("Error showing preview: %s", exc)


def _is_artist(user_id: int) -> bool:
    try:
        conn = _ctx("get_pg_connection")()
        if not conn:
            return False
        cursor = conn.cursor()
        try:
            cursor.execute('SELECT artist FROM label WHERE telegram_id = %s', (user_id,))
            row = cursor.fetchone()
            return bool(row and row[0])
        finally:
            cursor.close()
            _ctx("return_pg_connection")(conn)
    except Exception as exc:
        logger.error("Could not check artist role for %s: %s", user_id, exc)
        return False


def _process_improved_distribution_input(bot, message):
    forms = _forms(bot)
    user_id = message.from_user.id
    if user_id not in forms:
        return
    form = forms[user_id]
    step = form.get_current_step()
    if not step:
        return
    field_name, _, field_type = step
    if field_type == "photo":
        if message.photo:
            form.data[field_name] = message.photo[-1].file_id
    elif field_type == "audio":
        if message.audio or message.document:
            form.data[field_name] = message.audio.file_id if message.audio else message.document.file_id
    elif field_type == "document":
        if message.document:
            form.data[field_name] = message.document.file_id
    else:
        form.data[field_name] = message.text
    form.data = normalize_distribution_draft_data(form.data)
    if form.current_step < len(form.steps) - 1:
        form.current_step += 1
    _show_improved_distribution_step(bot, form.chat_id, form.message_id, form)
    bot.register_next_step_handler(message, lambda next_message: _process_improved_distribution_input(bot, next_message))


def _form_to_legacy_user_data(form) -> dict:
    data = dict(getattr(form, "data", {}) or {})
    data.setdefault("release_type", data.get("releaseType") or "Single")
    data.setdefault("artist_name", data.get("artistName") or data.get("artist_name") or "")
    data.setdefault("release_name", data.get("releaseName") or data.get("release_name") or "")
    data.setdefault("release_date", data.get("releaseDate") or data.get("release_date") or "")
    data.setdefault("performer_name", data.get("performerName") or data.get("performer_name") or data.get("artist_name") or "")
    data.setdefault("music_author", data.get("musicAuthor") or data.get("music_author") or data.get("artist_name") or "")
    data.setdefault("producer", data.get("producer") or "")
    data.setdefault("genre", data.get("genre") or "")
    data.setdefault("explicit_content", data.get("explicitContent") or data.get("explicit_content") or "Нет")
    data.setdefault("yandex_soon", data.get("yandexSoon") or data.get("yandex_soon") or "Нет")
    data.setdefault("create_links", data.get("createLinks") or data.get("create_links") or "Нет")
    data.setdefault("tiktok_commercial", data.get("tiktokCommercial") or data.get("tiktok_commercial") or "Нет")
    data.setdefault("tiktok_full_version", data.get("tiktokFullVersion") or data.get("tiktok_full_version") or "Нет")
    data.setdefault("preview_start", data.get("previewStart") or data.get("preview_start"))
    return data


def register_legacy_distribution_handlers(bot, context: dict | None = None) -> None:
    steps.configure_legacy_distribution_steps(bot=bot, **(context or {}))
    @bot.callback_query_handler(func=lambda call: call.data == "service_distribution")
    def handle_distribution_service(call):
        user_id = call.from_user.id
        is_complete, missing_field = _ctx("is_profile_complete")(user_id)
        if not is_complete:
            if missing_field == "name":
                bot.answer_callback_query(
                    call.id,
                    "❌ Перед отгрузкой необходимо заполнить профиль. Укажите ник артиста в разделе 'Профиль' → 'Редактировать профиль'",
                    show_alert=True,
                )
            else:
                bot.answer_callback_query(call.id, f"❌ Ошибка: {missing_field}", show_alert=True)
            return
        steps.show_distribution_agreement(call.message)

    @bot.callback_query_handler(func=lambda call: call.data == "distribution_disagree")
    def handle_distribution_disagree(call):
        bot.edit_message_text(
            "Для использования услуги дистрибуции необходимо согласие со всеми условиями. "
            "Если у вас есть вопросы, обратитесь в поддержку.",
            call.message.chat.id,
            call.message.message_id,
        )

    @bot.callback_query_handler(func=lambda call: call.data == "distribution_agree")
    def handle_distribution_agree(call):
        steps.handle_distribution_agree(call)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("distribution_pay_"))
    def handle_distribution_pay(call):
        steps.handle_distribution_pay(call)

    @bot.callback_query_handler(func=lambda call: call.data == "distribution_start")
    def start_distribution_form(call):
        steps.start_distribution_form(call)

    @bot.callback_query_handler(func=lambda call: call.data == "distribution_prev")
    def handle_distribution_prev(call):
        steps.handle_distribution_prev(call)

    @bot.callback_query_handler(func=lambda call: call.data == "distribution_next")
    def handle_distribution_next(call):
        steps.handle_distribution_next(call)

    @bot.callback_query_handler(func=lambda call: call.data == "distribution_edit")
    def handle_distribution_edit(call):
        steps.handle_distribution_edit(call)

    @bot.callback_query_handler(func=lambda call: call.data == "distribution_complete")
    def handle_distribution_complete(call):
        steps.handle_distribution_complete(call)

    @bot.callback_query_handler(func=lambda call: call.data == "use_promo_distribution")
    def handle_use_promo_distribution(call):
        steps.handle_use_promo_distribution(call)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("apply_promo_dist_"))
    def handle_apply_promo_distribution(call):
        steps.handle_apply_promo_distribution(call)

    @bot.message_handler(func=lambda message: getattr(message, "text", None) == "💾 Сохранить черновик")
    def handle_save_draft_button(message):
        user_id = message.from_user.id
        if user_id in bot.user_data and bot.user_data[user_id]:
            steps.save_draft_at_any_step(message)
        else:
            bot.send_message(
                message.chat.id,
                "❌ Нет данных для сохранения. Начните создание релиза заново.",
                reply_markup=_ctx("create_main_menu")(),
            )

    @bot.callback_query_handler(func=lambda call: call.data == "idist_start")
    def improved_distribution_start(call):
        form = ImprovedDistributionForm()
        form.chat_id = call.message.chat.id
        form.message_id = call.message.message_id
        form.user_id = call.from_user.id
        _forms(bot)[call.from_user.id] = form
        _show_improved_distribution_step(bot, form.chat_id, form.message_id, form)
        bot.register_next_step_handler(call.message, lambda message: _process_improved_distribution_input(bot, message))

    @bot.callback_query_handler(func=lambda call: call.data == "idist_prev")
    def improved_dist_prev(call):
        form = _forms(bot).get(call.from_user.id)
        if not form:
            return
        if form.current_step > 0:
            form.current_step -= 1
        _show_improved_distribution_step(bot, form.chat_id, form.message_id, form)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == "idist_next")
    def improved_dist_next(call):
        form = _forms(bot).get(call.from_user.id)
        if not form:
            return
        if form.current_step < len(form.steps) - 1 and form.has_answer():
            form.current_step += 1
        _show_improved_distribution_step(bot, form.chat_id, form.message_id, form)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == "idist_edit")
    def improved_dist_edit(call):
        form = _forms(bot).get(call.from_user.id)
        if not form:
            return
        step = form.get_current_step()
        if step:
            form.data.pop(step[0], None)
        _show_improved_distribution_step(bot, form.chat_id, form.message_id, form)
        bot.answer_callback_query(call.id, "Введите новое значение")

    @bot.callback_query_handler(func=lambda call: call.data.startswith("idist_yes_") or call.data.startswith("idist_no_"))
    def improved_dist_yes_no(call):
        form = _forms(bot).get(call.from_user.id)
        if not form:
            return
        parts = call.data.split("_")
        answer = "Да" if parts[1] == "yes" else "Нет"
        field_name = "_".join(parts[2:])
        form.data[field_name] = answer
        form.data = normalize_distribution_draft_data(form.data)
        if form.current_step < len(form.steps) - 1:
            form.current_step += 1
        _show_improved_distribution_step(bot, form.chat_id, form.message_id, form)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == "idist_cancel_all")
    def improved_dist_cancel_all(call):
        form = _forms(bot).get(call.from_user.id)
        if not form:
            return
        if form.data:
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("💾 Да, сохранить", callback_data="idist_save_and_cancel"),
                types.InlineKeyboardButton("❌ Нет, удалить", callback_data="idist_delete_and_cancel"),
            )
            try:
                bot.edit_message_text("❌ Отмена создания релиза\n\nСохранить как черновик?", form.chat_id, form.message_id, reply_markup=markup)
            except Exception:
                pass
        else:
            _forms(bot).pop(call.from_user.id, None)
            bot.answer_callback_query(call.id, "❌ Отменено")

    @bot.callback_query_handler(func=lambda call: call.data == "idist_save_draft")
    def improved_dist_save_draft(call):
        form = _forms(bot).get(call.from_user.id)
        if not form:
            return
        try:
            saved_id = save_user_draft(call.from_user.id, "distribution", form.data, form.current_step)
            if not saved_id:
                raise RuntimeError("draft was not saved")
            bot.answer_callback_query(call.id, "✅ Черновик сохранён!")
            _forms(bot).pop(call.from_user.id, None)
            try:
                bot.edit_message_text("💾 Черновик сохранён!\n\nВы можете продолжить заполнение позже из раздела 'Черновики' в профиле.", form.chat_id, form.message_id)
            except Exception:
                pass
        except Exception as exc:
            logger.error("Error saving draft: %s", exc)
            bot.answer_callback_query(call.id, "❌ Ошибка сохранения")

    @bot.callback_query_handler(func=lambda call: call.data == "idist_save_and_cancel")
    def improved_dist_save_and_cancel(call):
        improved_dist_save_draft(call)

    @bot.callback_query_handler(func=lambda call: call.data == "idist_delete_and_cancel")
    def improved_dist_delete_and_cancel(call):
        forms = getattr(bot, "improved_distribution_forms", {})
        forms.pop(call.from_user.id, None)
        bot.answer_callback_query(call.id, "❌ Отменено")
        try:
            bot.edit_message_text("❌ Создание релиза отменено.", call.message.chat.id, call.message.message_id)
        except Exception:
            pass

    @bot.callback_query_handler(func=lambda call: call.data == "idist_preview")
    def improved_dist_preview(call):
        form = _forms(bot).get(call.from_user.id)
        if not form:
            return
        _show_improved_distribution_preview(bot, form.chat_id, form.message_id, form)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == "idist_edit_back")
    def improved_dist_edit_back(call):
        form = _forms(bot).get(call.from_user.id)
        if not form:
            return
        form.current_step = len(form.steps) - 1
        _show_improved_distribution_step(bot, form.chat_id, form.message_id, form)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda call: call.data == "idist_submit_free")
    def improved_dist_submit_free(call):
        form = getattr(bot, "improved_distribution_forms", {}).get(call.from_user.id)
        if not form:
            bot.answer_callback_query(call.id, "Форма не найдена", show_alert=True)
            return
        if not _is_artist(call.from_user.id):
            bot.answer_callback_query(call.id, "Бесплатная отправка доступна только артистам лейбла", show_alert=True)
            return
        bot.user_data[call.from_user.id] = _form_to_legacy_user_data(form)
        bot.answer_callback_query(call.id)
        steps.save_release_data_for_user(call.from_user.id, call.message.chat.id)
        getattr(bot, "improved_distribution_forms", {}).pop(call.from_user.id, None)

    @bot.callback_query_handler(func=lambda call: call.data == "idist_pay")
    def improved_dist_pay(call):
        form = getattr(bot, "improved_distribution_forms", {}).get(call.from_user.id)
        if not form:
            bot.answer_callback_query(call.id, "Форма не найдена", show_alert=True)
            return
        bot.user_data[call.from_user.id] = _form_to_legacy_user_data(form)
        bot.answer_callback_query(call.id)
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("Подтвердить оплату", callback_data="distribution_pay_1299"))
        markup.add(types.InlineKeyboardButton("🎟 Использовать промокод", callback_data="use_promo_distribution"))
        bot.edit_message_text("Подтвердите списание 1299₽ за Single.", call.message.chat.id, call.message.message_id, reply_markup=markup)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("draft_load_"))
    def handle_draft_load(call):
        raw_draft_id = call.data.replace("draft_load_", "", 1).strip()
        if not raw_draft_id.isdigit():
            bot.answer_callback_query(call.id, "❌ Неверный черновик", show_alert=True)
            return
        draft = get_user_draft(int(raw_draft_id), call.from_user.id)
        if not draft:
            bot.answer_callback_query(call.id, "❌ Черновик не найден", show_alert=True)
            return
        data = normalize_distribution_draft_data(draft.get("data") or {})
        draft_type = draft.get("draft_type")
        if draft_type in {"distribution_legacy", "single", "album", "release"}:
            data["draft_id"] = draft["id"]
            data["from_draft"] = True
            bot.user_data[call.from_user.id] = data
            bot.answer_callback_query(call.id, "✅ Черновик загружен")
            fake_message = type("Msg", (), {
                "chat": type("C", (), {"id": call.message.chat.id})(),
                "from_user": type("U", (), {"id": call.from_user.id})(),
            })()
            steps.show_release_preview(fake_message, data, from_draft=True)
            return
        if draft_type == "distribution":
            form = ImprovedDistributionForm()
            form.chat_id = call.message.chat.id
            form.message_id = call.message.message_id
            form.user_id = call.from_user.id
            form.data = data
            form.current_step = min(int(draft.get("current_step") or 0), len(form.steps) - 1)
            _forms(bot)[call.from_user.id] = form
            bot.answer_callback_query(call.id, "✅ Черновик загружен")
            _show_improved_distribution_step(bot, form.chat_id, form.message_id, form)
            bot.register_next_step_handler(call.message, lambda message: _process_improved_distribution_input(bot, message))
            return
        bot.answer_callback_query(call.id, "❌ Тип черновика не поддерживается", show_alert=True)

    @bot.callback_query_handler(func=lambda call: call.data.startswith("edit_release_name_"))
    def handle_edit_release_name(call):
        _legacy().handle_edit_release_name(call)
