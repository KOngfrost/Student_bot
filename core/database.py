import asyncio
import re
import time
from collections.abc import AsyncIterator

import asyncpg
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from core.config import settings

engine = create_async_engine(settings.database_url, echo=False, poolclass=pool.NullPool)
async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


async def ensure_database_exists(max_retries: int = 10, retry_delay: float = 2.0) -> None:
    if not DATABASE_NAME_PATTERN.fullmatch(settings.DB_NAME):
        raise ValueError("DB_NAME содержит недопустимые символы")

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
    await engine.dispose()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with async_session_maker() as session:
        yield session