"""Общие фикстуры тестов: in-memory SQLite вместо PostgreSQL."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Секрет обязателен для импорта web.main
os.environ.setdefault("SESSION_SECRET_KEY", "test_secret_key_for_tests_1234567890")

import pytest_asyncio  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

import core.database as database_module  # noqa: E402
import core.outbox as outbox_module  # noqa: E402
import core.reporting as reporting_module  # noqa: E402
import core.ticket_service as ticket_service_module  # noqa: E402
from core.models import Base  # noqa: E402


@pytest_asyncio.fixture
async def db_session_maker():
    """Async session maker на in-memory SQLite с подменой во всех модулях."""
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    originals = [
        (database_module, database_module.async_session_maker),
        (ticket_service_module, ticket_service_module.async_session_maker),
        (reporting_module, reporting_module.async_session_maker),
        (outbox_module, outbox_module.async_session_maker),
    ]
    database_module.async_session_maker = maker
    ticket_service_module.async_session_maker = maker
    reporting_module.async_session_maker = maker
    outbox_module.async_session_maker = maker

    yield maker

    for module, original in originals:
        module.async_session_maker = original
    await engine.dispose()
