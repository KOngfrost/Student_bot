"""Общие фикстуры тестов: in-memory SQLite вместо PostgreSQL."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Секрет обязателен для импорта web.main
os.environ.setdefault("SESSION_SECRET_KEY", "test_secret_key_for_tests_1234567890")
# Тесты не должны зависеть от production-настроек локального .env.
os.environ["APP_ENV"] = "development"
os.environ["SESSION_HTTPS_ONLY"] = "false"

import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import core.database as database_module
import core.outbox as outbox_module
import core.reporting as reporting_module
import core.ticket_service as ticket_service_module
from core.models import Base


@pytest_asyncio.fixture
async def db_session_maker(monkeypatch):
    """Async session maker на in-memory SQLite с подменой во всех модулях.

    Подмена выполняется через monkeypatch: pytest гарантированно
    восстанавливает исходные атрибуты модулей даже при падении теста.
    ВАЖНО: паттерн с подменой атрибутов модулей несовместим с запуском
    тестов в нескольких потоках одного процесса; при распараллеливании
    используйте отдельные процессы (pytest-xdist) либо рефакторинг
    сервисов на явную передачу session-factory.
    """
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    for module in (database_module, ticket_service_module, reporting_module, outbox_module):
        monkeypatch.setattr(module, "async_session_maker", maker, raising=True)

    yield maker

    await engine.dispose()
