"""Small security and upload-validation helpers shared by legacy and modular code."""
from __future__ import annotations

import os


def escape_html(text: object) -> str:
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_markdown(text: object) -> str:
    if text is None:
        return ""
    escape_chars = r"_ * [ ] ( ) ~ ` > # + - = | { } . !".split()
    escaped = str(text)
    for char in escape_chars:
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def validate_file_upload(message, allowed_extensions=None, max_size_mb: int = 10, required_type: str = "document"):
    """Validate a Telegram upload message and return (ok, error, file_id)."""
    if required_type == "document" and not getattr(message, "document", None):
        return False, "❌ Пожалуйста, отправьте файл", None
    if required_type == "photo" and not getattr(message, "photo", None):
        return False, "❌ Пожалуйста, отправьте изображение", None
    if required_type == "audio" and not getattr(message, "audio", None):
        return False, "❌ Пожалуйста, отправьте аудиофайл", None
    if required_type == "video" and not getattr(message, "video", None):
        return False, "❌ Пожалуйста, отправьте видеофайл", None

    if required_type == "document":
        upload = message.document
        file_id = upload.file_id
        file_name = upload.file_name or ""
        file_size = upload.file_size or 0
    elif required_type == "photo":
        file_id = message.photo[-1].file_id
        file_name = "photo.jpg"
        file_size = 0
    elif required_type == "audio":
        upload = message.audio
        file_id = upload.file_id
        file_name = upload.file_name or ""
        file_size = upload.file_size or 0
    elif required_type == "video":
        upload = message.video
        file_id = upload.file_id
        file_name = upload.file_name or ""
        file_size = upload.file_size or 0
    else:
        return False, "❌ Неподдерживаемый тип файла", None

    if file_size > 0 and file_size > max_size_mb * 1024 * 1024:
        return False, f"❌ Файл слишком большой! Максимальный размер: {max_size_mb} МБ", None

    if allowed_extensions and file_name:
        file_ext = os.path.splitext(file_name.lower())[1]
        if file_ext not in allowed_extensions:
            return False, f"❌ Неподдерживаемый формат файла. Разрешены: {', '.join(allowed_extensions)}", None

    return True, "", file_id
