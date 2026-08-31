"""Тесты конфигурации."""

from zoneinfo import ZoneInfo

from core.config import settings
from core.reporting import get_app_tz


def test_database_url_uses_asyncpg():
    assert settings.database_url.startswith("postgresql+asyncpg://")


def test_app_timezone_default_is_moscow():
    assert settings.APP_TIMEZONE == "Europe/Moscow"


def test_get_app_tz_returns_valid_zone():
    tz = get_app_tz()
    assert isinstance(tz, ZoneInfo)
    assert str(tz) == "Europe/Moscow"


def test_allow_db_create_disabled_by_default():
    # В production приложение не должно само создавать базу
    assert settings.ALLOW_DB_CREATE is False


def test_report_time_format():
    assert ":" in settings.REPORT_TIME
    hours, minutes = settings.REPORT_TIME.split(":")
    assert 0 <= int(hours) <= 23
    assert 0 <= int(minutes) <= 59
