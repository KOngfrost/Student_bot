"""Опциональные интеграционные проверки PostgreSQL."""

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.asyncio
async def test_postgres_connection():
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL не задан")

    engine = create_async_engine(url)
    try:
        async with engine.connect() as connection:
            result = await connection.scalar(text("SELECT 1"))
        assert result == 1
    finally:
        await engine.dispose()