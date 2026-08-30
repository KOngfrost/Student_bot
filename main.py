import asyncio
import logging
import socket
import time

import aiohttp
from vkbottle.exception_factory.base_exceptions import VKAPIError

from bots.vk.bot import vk_bot
from core.config import settings
from core.database import ensure_database_exists, run_migrations
from core.reporting import start_report_scheduler

logger = logging.getLogger(__name__)


def initialize_database() -> None:
    asyncio.run(ensure_database_exists())
    run_migrations()


async def _start_scheduler() -> None:
    """Запускает asyncio-планировщик отчётов в event loop бота."""
    start_report_scheduler(vk_bot.api, settings.VK_REPORT_ADMIN_ID)
    logger.info("Планировщик отчётов запущен")


# Флаг для предотвращения дублирования scheduler при retry polling
_scheduler_started = False


def run_vk_polling() -> None:
    retry_delay = 5

    while True:
        try:
            global _scheduler_started
            if not _scheduler_started:
                vk_bot.on_startup.append(_start_scheduler())
                _scheduler_started = True
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