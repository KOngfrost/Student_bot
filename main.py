import asyncio
import logging
import socket
import time

import aiohttp
from vkbottle.exception_factory.base_exceptions import VKAPIError

from bots.vk.bot import vk_bot
from core.config import settings
from core.database import run_migrations
from core.heartbeat import touch_heartbeat
from core.reporting import start_report_scheduler

logger = logging.getLogger(__name__)


def initialize_database() -> None:
    """Применяет Alembic-миграции.

    В production схему создаёт только Alembic; базу создаёт PostgreSQL-
    контейнер (POSTGRES_DB). Автосоздание базы приложением (ensure_database_exists)
    включается только в dev через ALLOW_DB_CREATE=true.
    """
    if settings.ALLOW_DB_CREATE:
        from core.database import ensure_database_exists

        asyncio.run(ensure_database_exists())
    run_migrations()


async def _start_scheduler() -> None:
    """Запускает asyncio-планировщик отчётов, outbox-воркер и heartbeat."""
    start_report_scheduler(vk_bot.api, settings.VK_REPORT_ADMIN_ID)
    logger.info("Планировщик отчётов запущен")

    # Outbox: доставка VK-уведомлений, записанных в ту же транзакцию,
    # что и изменения заявок (см. core/outbox.py).
    from core.outbox import outbox_worker_loop

    asyncio.create_task(outbox_worker_loop())

    # Периодическое обновление heartbeat для docker healthcheck
    async def _heartbeat_loop() -> None:
        while True:
            touch_heartbeat()
            await asyncio.sleep(60)

    asyncio.create_task(_heartbeat_loop())


def run_vk_polling() -> None:
    retry_delay = 5

    while True:
        try:
            # vkbottle очищает on_startup после каждого run(),
            # поэтому добавляем свежую coroutine перед каждым запуском
            vk_bot.on_startup.append(_start_scheduler())
            vk_bot.run()
            logger.warning("VK polling stopped; retrying in %s seconds", retry_delay)
        except (aiohttp.ClientError, OSError, socket.gaierror, TimeoutError) as error:
            logger.error(
                "VK polling is unavailable: %s; retrying in %s seconds",
                error,
                retry_delay,
            )

        time.sleep(retry_delay)
        retry_delay = min(retry_delay * 2, 300)


def run() -> None:
    try:
        settings.ensure_production_config()
        initialize_database()
        run_vk_polling()
    except VKAPIError as error:
        if "longpoll" in str(error).lower():
            print(
                "VK Long Poll отключен. Включите его в настройках сообщества: "
                "Управление сообществом > Работа с API > Long Poll API."
            )
            print(
                "В разделе Long Poll API включите API и события сообщений, "
                "затем проверьте права токена сообщества."
            )
            return
        raise


if __name__ == "__main__":
    run()