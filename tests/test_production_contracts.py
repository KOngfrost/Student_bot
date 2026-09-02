"""Регрессионные проверки production-контрактов приложения."""

import json

import pytest

from bots.vk.keyboards import build_admin_keyboard, build_main_keyboard
from core.config import Settings


def _labels(keyboard: str) -> list[str]:
    data = json.loads(keyboard)
    return [button["action"]["label"] for row in data["buttons"] for button in row]


def test_regular_menu_never_contains_admin_actions():
    labels = _labels(build_main_keyboard(is_admin=True))

    assert "Заявки администратора" not in labels
    assert "Сформировать отчет" not in labels
    assert "Отчет по дате" not in labels
    assert "Отчет за период" not in labels
    assert "Обычное меню" not in labels
    assert "Мои заявки" in labels


def test_admin_menu_is_separate_from_regular_menu():
    labels = _labels(build_admin_keyboard())

    assert labels == [
        "Заявки администратора",
        "Сформировать отчет",
        "Отчет по дате",
        "Отчет за период",
        "Обычное меню",
    ]


def _production_settings(**values: str) -> Settings:
    settings = object.__new__(Settings)
    settings.APP_ENV = "production"
    settings.DB_USER = values.get("DB_USER", "production_user")
    settings.DB_PASS = values.get("DB_PASS", "long-production-password")
    settings.SESSION_SECRET_KEY = values.get(
        "SESSION_SECRET_KEY", "x" * 64
    )
    return settings


def test_production_configuration_accepts_explicit_secure_values():
    _production_settings().ensure_production_config()


@pytest.mark.parametrize(
    "field,value",
    [
        ("DB_USER", "student_bot"),
        ("DB_PASS", "student_bot"),
        ("SESSION_SECRET_KEY", "too-short"),
    ],
)
def test_production_configuration_rejects_insecure_defaults(field: str, value: str):
    with pytest.raises(RuntimeError):
        _production_settings(**{field: value}).ensure_production_config()