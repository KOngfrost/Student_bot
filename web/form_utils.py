"""Мелкие утилиты разбора форм веб-панели."""

from typing import Any


def parse_form_int(form: dict, key: str, default: int | None = None) -> int | None:
    """Безопасно разобрать целое число из формы.

    Пустая строка, отсутствие поля и нечисловое значение возвращают
    ``default`` вместо ValueError → маршруты не падают с 500.
    """
    raw = form.get(key)
    if raw is None:
        return default
    text = str(raw).strip()
    if not text:
        return default
    try:
        return int(text)
    except ValueError:
        return default


def clipped(text: Any, limit: int) -> str:
    """Обрезать строку до ``limit`` символов с многоточием (для таблиц)."""
    value = "" if text is None else str(text)
    if len(value) <= limit:
        return value
    return value[:limit] + "…"
