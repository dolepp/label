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


def render_saved_template(user_data: dict):
    """Use the owner's preserved licensing template for the existing bot wizard."""
    import importlib.util
    from pathlib import Path
    from uuid import uuid4
    from docx import Document

    path = Path(__file__).resolve().parents[2] / 'site/contract_documents.py'
    spec = importlib.util.spec_from_file_location('label_contract_documents', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    profile = {key: str(user_data.get(key) or '') for key in module.FIELDS}
    profile = {key: '' if value in {'N/A', 'Не указано'} else value for key, value in profile.items()}
    release = {'id': uuid4().hex[:12], 'release_name': user_data.get('release_name'),
               'artist_name': user_data.get('nickname')}
    track = dict(release, track_name=user_data.get('track_name'),
                 release_name=user_data.get('track_name') or user_data.get('release_name'),
                 music_author=user_data.get('music_author'), text_author=user_data.get('text_author'),
                 performer_name=user_data.get('performer'), phonogram_producer=user_data.get('phonogram_producer'))
    output, _ = module.render_contract(profile, release, [track], contract_date=user_data.get('date') if user_data.get('date') not in {None, '', 'N/A'} else None)
    return Document(output)


def generate_release_contract(connection, account_id: int, release_id: int):
    """Reuse details saved in the cabinet when a release is submitted in the bot."""
    import os
    import sys
    from pathlib import Path
    from psycopg2.extras import RealDictCursor

    site = Path(__file__).resolve().parents[2] / 'site'
    if str(site) not in sys.path: sys.path.append(str(site))
    from contract_store import profile_cipher, read_contract_profile, generate_owned_contract
    root = Path(os.getenv('MEDIA_STORAGE_ROOT', site.parent / 'storage'))
    cursor = connection.cursor(cursor_factory=RealDictCursor)
    try:
        cipher = profile_cipher()
        if not read_contract_profile(cursor, account_id, cipher):
            connection.rollback()
            return None
        result = generate_owned_contract(cursor, account_id, release_id, root, cipher)
        connection.commit()
        return root / result['relative_path']
    except Exception:
        connection.rollback()
        raise
    finally: cursor.close()
