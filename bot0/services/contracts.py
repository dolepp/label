"""Contract flow helpers shared by legacy handlers."""
from __future__ import annotations

import re


SUMMARY_FIELDS = (
    ("📅 Дата договора", "date"),
    ("👤 ФИО", "full_name"),
    ("🆔 Паспорт", "passport"),
    ("🎭 Псевдоним", "nickname"),
    ("🏛️ Кем выдан", "passport_issued"),
    ("📅 Дата выдачи", "issue_date"),
    ("🔢 Код подразделения", "department_code"),
    ("🎂 Дата рождения", "birth_date"),
    ("🌍 Место рождения", "birth_place"),
    ("🏠 Адрес", "address"),
    ("📋 СНИЛС", "snils"),
    ("🔢 ИНН", "inn"),
    ("💿 Релиз", "release_name"),
    ("🎵 Трек", "track_name"),
    ("🎼 Автор музыки", "music_author"),
    ("📝 Автор текста", "text_author"),
    ("🎤 Исполнитель", "performer"),
    ("🎧 Изготовитель фонограммы", "phonogram_producer"),
)


def build_contract_summary(contract_data: dict) -> str:
    lines = ["📋 Проверьте введенные данные:", ""]
    for label, key in SUMMARY_FIELDS:
        lines.append(f"{label}: {contract_data.get(key, 'Не указано')}")
    lines.extend(["", "✅ Всё верно?"])
    return "\n".join(lines)


def normalize_contract_data(contract_data: dict) -> dict:
    normalized = {}
    for key, value in contract_data.items():
        if value is None or value == "":
            normalized[key] = "N/A"
        elif not isinstance(value, str):
            normalized[key] = str(value)
        elif value.strip() == "":
            normalized[key] = "N/A"
        else:
            normalized[key] = value
    return normalized


def contract_filename(nickname: str | None) -> str:
    if nickname and nickname != "N/A":
        safe_nickname = re.sub(r'[<>:"/\\|?*]', "_", str(nickname))
        return f"Лицензионный_договор_{safe_nickname}.docx"
    return "Лицензионный_договтор.docx"
