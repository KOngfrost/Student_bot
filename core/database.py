import asyncio
import re
import time
from collections.abc import AsyncIterator

import asyncpg
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)

from core.config import settings

# Подключение к БД работает как в исходной версии проекта: NullPool —
# по одному подключению на каждый запрос, без пула на стороне приложения.
if settings.database_url:
    engine = create_async_engine(settings.database_url, echo=False, poolclass=pool.NullPool)
else:
    # Учётные данные не заданы (например, в CI): движок не создаём,
    # тесты используют свой in-memory SQLite (см. tests/conftest.py).
    engine = None
async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
) if engine is not None else None

# Строгая валидация имени базы данных.
# - Начинается с буквы или подчёркивания
# - Только буквы, цифры, подчёркивания
# - Максимум 63 символа (лимит PostgreSQL)
# - Не начинается с цифры (невозможно в PostgreSQL anyway)
# - Не содержит пробелов, дефисов, спецсимволов
DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

# Зарезервированные имена PostgreSQL, которые нельзя использовать
POSTGRES_RESERVED_DB_NAMES = {
    "postgres", "template0", "template1",
}


async def ensure_database_exists(max_retries: int = 10, retry_delay: float = 2.0) -> None:
    if not DATABASE_NAME_PATTERN.fullmatch(settings.DB_NAME):
        raise ValueError(
            f"DB_NAME содержит недопустимые символы: {settings.DB_NAME!r}. "
            "Разрешены только буквы, цифры и подчёркивания (макс. 63 символа)."
        )

    # Защита от использования зарезервированных имён PostgreSQL
    if settings.DB_NAME.lower() in POSTGRES_RESERVED_DB_NAMES:
        raise ValueError(
            f"DB_NAME '{settings.DB_NAME}' — зарезервированное имя PostgreSQL. "
            "Используйте другое имя базы данных."
        )

    last_error = None

    for attempt in range(1, max_retries + 1):
        admin_conn = None
        try:
            admin_conn = await asyncpg.connect(
                user=settings.DB_USER,
                password=settings.DB_PASS,
                database="postgres",
                host=settings.DB_HOST,
                port=int(settings.DB_PORT),
            )
            db_exists = await admin_conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1",
                settings.DB_NAME,
            )
            if not db_exists:
                await admin_conn.execute(f'CREATE DATABASE "{settings.DB_NAME}"')
            return
        except Exception as exc:
            last_error = exc
            if attempt == max_retries:
                raise
            await asyncio.sleep(retry_delay)
        finally:
            if admin_conn is not None:
                await admin_conn.close()

    if last_error is not None:
        raise last_error


def run_migrations(max_retries: int = 5, retry_delay: float = 2.0) -> None:
    """Apply Alembic migrations to the database."""
    from alembic import command
    from alembic.config import Config

    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            alembic_cfg = Config("alembic.ini")
            command.upgrade(alembic_cfg, "head")
            return
        except Exception as exc:
            last_error = exc
            if attempt == max_retries:
                raise
            time.sleep(retry_delay)

    if last_error is not None:
        raise last_error


async def dispose_engine() -> None:
    if engine is not None:
        await engine.dispose()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        yield session