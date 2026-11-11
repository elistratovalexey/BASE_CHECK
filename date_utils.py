# date_utils.py
"""Хранение дат в БД — ISO (yyyy-MM-dd), отображение и ввод — дд-мм-гггг."""
from datetime import datetime

DISPLAY_FORMAT = "%d-%m-%Y"
ISO_FORMAT = "%Y-%m-%d"
QT_DISPLAY = "dd-MM-yyyy"
QT_ISO = "yyyy-MM-dd"

_FORMATS = (ISO_FORMAT, "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%Y")


def to_display(value) -> str:
    if not value:
        return ""
    value = str(value).strip()
    for fmt in _FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime(DISPLAY_FORMAT)
        except ValueError:
            continue
    return value


def to_iso(value) -> str:
    if not value:
        return ""
    value = str(value).strip()
    for fmt in _FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime(ISO_FORMAT)
        except ValueError:
            continue
    return value