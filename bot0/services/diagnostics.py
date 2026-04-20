"""Runtime diagnostics for admin commands."""
from __future__ import annotations

import importlib.util
from datetime import datetime

import requests

from core.config import CHANNEL_USERNAME
from db.pool import connection


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def check_postgres() -> dict:
    try:
        with connection() as conn:
            if conn is None:
                return {"name": "PostgreSQL", "ok": False, "details": "Не удалось подключиться к базе данных"}
            cur = conn.cursor()
            try:
                cur.execute("SELECT 1")
                cur.fetchone()
            finally:
                cur.close()
        return {"name": "PostgreSQL", "ok": True, "details": "Соединение установлено"}
    except Exception as exc:
        return {"name": "PostgreSQL", "ok": False, "details": f"Ошибка: {exc}"}


def check_telegram_api(bot) -> dict:
    try:
        bot_info = bot.get_me()
        return {"name": "Telegram API", "ok": True, "details": f"Подключен как @{bot_info.username}"}
    except Exception as exc:
        return {"name": "Telegram API", "ok": False, "details": f"Ошибка: {exc}"}


def check_channel_access(bot) -> dict:
    try:
        bot.get_chat(CHANNEL_USERNAME)
        bot_member = bot.get_chat_member(CHANNEL_USERNAME, bot.get_me().id)
        ok = bot_member.status in ("administrator", "creator")
        return {
            "name": "Канал Telegram",
            "ok": ok,
            "details": "Доступ подтвержден" if ok else "Нет доступа к каналу или прав администратора",
        }
    except Exception as exc:
        return {"name": "Канал Telegram", "ok": False, "details": f"Ошибка: {exc}"}


def check_yookassa() -> dict:
    try:
        from yookassa import Configuration
    except ImportError:
        return {"name": "YooKassa API", "ok": False, "details": "YooKassa module not available"}

    if not Configuration.account_id or not Configuration.secret_key:
        return {"name": "YooKassa API", "ok": False, "details": "YooKassa credentials not configured"}

    try:
        response = requests.get(
            "https://api.yookassa.ru/v3/me",
            auth=(Configuration.account_id, Configuration.secret_key),
            timeout=10,
        )
        if response.status_code == 200:
            return {"name": "YooKassa API", "ok": True, "details": "YooKassa API is accessible"}
        return {"name": "YooKassa API", "ok": False, "details": f"YooKassa API returned status {response.status_code}"}
    except Exception as exc:
        return {"name": "YooKassa API", "ok": False, "details": f"YooKassa API check failed: {exc}"}


def perform_system_diagnostics(bot) -> tuple[list[dict], bool]:
    diagnostics = [
        check_telegram_api(bot),
        check_channel_access(bot),
        check_postgres(),
        check_yookassa(),
        {
            "name": "python-docx",
            "ok": _module_available("docx"),
            "details": "Модуль доступен" if _module_available("docx") else "Модуль недоступен, генерация .docx отключена",
        },
        {
            "name": "openpyxl",
            "ok": _module_available("openpyxl"),
            "details": "Модуль доступен" if _module_available("openpyxl") else "Модуль недоступен, генерация .xlsx отключена",
        },
        {
            "name": "schedule",
            "ok": _module_available("schedule"),
            "details": "Планировщик активен" if _module_available("schedule") else "Модуль schedule не найден",
        },
    ]
    return diagnostics, all(item["ok"] for item in diagnostics)


def diagnostics_text(diagnostics: list[dict], overall_status: bool, now: datetime | None = None) -> str:
    current = now or datetime.now()
    response_lines = [
        "🩺 Автоматическая проверка систем завершена",
        f"🕒 {current.strftime('%d.%m.%Y %H:%M:%S')}",
        "",
    ]
    for item in diagnostics:
        icon = "✅" if item["ok"] else "❌"
        response_lines.append(f"{icon} {item['name']}: {item['details']}")
    response_lines.append("")
    response_lines.append("💡 Все системы работают штатно." if overall_status else "⚠️ Обнаружены проблемы, проверьте логи.")
    return "\n".join(response_lines)
