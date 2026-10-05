"""Release status normalisation shared by bot handlers.

The releases table holds statuses written by the bot ("принят"), the site admin
("Принят") and inserts ("pending"). Compare and display them through these helpers.
"""
from __future__ import annotations

_ALIASES = {
    "pending": "pending",
    "на рассмотрении": "pending",
    "в обработке": "pending",
    "на проверке": "pending",
    "accepted": "accepted",
    "принят": "accepted",
    "sent": "sent",
    "отправлен на площадки": "sent",
    "delivered": "delivered",
    "отгружен на площадки": "delivered",
    "released": "released",
    "релиз": "released",
    "withdrawn": "withdrawn",
    "отозван с площадок": "withdrawn",
    "rejected": "rejected",
    "отклонен": "rejected",
    "отклонён": "rejected",
}

_LABELS = {
    "pending": "На рассмотрении",
    "accepted": "Принят",
    "sent": "Отправлен на площадки",
    "delivered": "Отгружен на площадки",
    "released": "Релиз",
    "withdrawn": "Отозван с площадок",
    "rejected": "Отклонён",
}

# Пока релиз не ушёл на площадки, артист может поправить данные.
EDITABLE_RELEASE_STATUSES = {"pending", "accepted"}


def normalize_release_status(status: str | None) -> str:
    raw = str(status or "pending").strip().lower()
    return _ALIASES.get(raw, raw)


def release_status_label(status: str | None) -> str:
    key = normalize_release_status(status)
    return _LABELS.get(key, str(status or "").strip() or "На рассмотрении")


def is_release_editable(status: str | None) -> bool:
    return normalize_release_status(status) in EDITABLE_RELEASE_STATUSES
