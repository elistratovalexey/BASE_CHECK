# date_utils.py
"""Единый формат дат.
Хранение в БД — ISO (yyyy-MM-dd): от него корректно работают фильтр и сортировка.
Отображение и ввод пользователем — дд-мм-гггг.
Любой QDateEdit в программе должен вызывать setDisplayFormat(date_utils.QT_DISPLAY).
"""
from datetime import datetime

DISPLAY_FORMAT = "%d-%m-%Y"     # дд-мм-гггг (Python)
ISO_FORMAT = "%Y-%m-%d"         # гггг-мм-дд (Python)
QT_DISPLAY = "dd-MM-yyyy"       # дд-мм-гггг (Qt)
QT_ISO = "yyyy-MM-dd"           # гггг-мм-дд (Qt)

_FORMATS = (ISO_FORMAT, "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%Y")


def to_display(value) -> str:
    """ISO (или другой распознанный формат) -> дд-мм-гггг. Пусто -> ''."""
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
    """дд-мм-гггг (или другой распознанный формат) -> ISO для хранения. Пусто -> ''."""
    if not value:
        return ""
    value = str(value).strip()
    for fmt in _FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime(ISO_FORMAT)
        except ValueError:
            continue
    return value