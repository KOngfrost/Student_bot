"""Outbox: надёжная отправка VK-уведомлений.

Проблема, которую решает: раньше VK-сообщение уходило ДО фиксации
транзакции в БД. Если БД падала, студент получал ответ, которого нет
в истории заявки. Теперь:

1. Сообщение пишется в таблицу vk_outbox в ТОЙ ЖЕ транзакции,
   что и изменение заявки (commit гарантирует сохранение).
2. Фоновый воркер (в цикле бота и/или по расписанию веб-панели)
   доставляет отложенные сообщения через core.vk_client.send_vk_message.

Так мы получаем «at-least-once» доставку с ретраями вместо
«потерянного» ответа студенту.
"""

import asyncio
import logging
import os
from datetime import UTC, datetime

from sqlalchemy import select

from core.database import async_session_maker
from core.models import VkOutbox
from core.vk_client import OUTBOX_MAX_ATTEMPTS, send_vk_message

logger = logging.getLogger(__name__)

# Размер партии и частота опроса настраиваются в .env (OUTBOX_BATCH_SIZE,
# OUTBOX_INTERVAL_SECONDS). При нагрузке >2500 пользователей разумнее
# выносить больше сообщений за проход, чем делать частые мелкие опросы.
OUTBOX_BATCH_SIZE = int(os.getenv("OUTBOX_BATCH_SIZE", "50"))
OUTBOX_RETRY_DELAY_SECONDS = int(os.getenv("OUTBOX_INTERVAL_SECONDS", "30"))


# Ссылки на запущенные задачи доставки: без сильной ссылки GC может
# уничтожить задачу до её завершения
_delivery_tasks: set[asyncio.Task] = set()


def fire_outbox_delivery() -> None:
    """Запустить фоновую доставку outbox, если есть работающий event loop.

    Вызывается после commit() там, где нужно доставить сообщение «прямо сейчас»
    (ответ администратора в веб-панели). Если loop недоступен (тесты,
    синхронный контекст) — ничего страшного: доставит периодический воркер.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("Нет запущенного event loop — outbox доставит воркер")
        return
    task = asyncio.create_task(deliver_pending_messages())
    _delivery_tasks.add(task)
    task.add_done_callback(_delivery_tasks.discard)


def add_outbox_message(session, vk_id: int, text: str) -> VkOutbox:
    """Добавить сообщение в outbox в текущей транзакции (без commit)."""
    entry = VkOutbox(vk_id=vk_id, text=text, status="pending", attempts=0)
    session.add(entry)
    return entry


async def deliver_pending_messages(
    batch_size: int = OUTBOX_BATCH_SIZE,
) -> int:
    """Доставить одну партию отложенных сообщений. Возвращает число попыток."""
    delivered = 0
    async with async_session_maker() as session:
        pending = await session.scalars(
            select(VkOutbox)
            .where(VkOutbox.status == "pending")
            .order_by(VkOutbox.created_at.asc(), VkOutbox.id.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        for message in pending:
            ok = await send_vk_message(message.vk_id, message.text)
            message.attempts += 1
            if ok:
                message.status = "sent"
                message.sent_at = datetime.now(UTC)
                message.error = None
                delivered += 1
                logger.info("Outbox: сообщение #%s доставлено vk_id=%s", message.id, message.vk_id)
            else:
                message.error = "VK API недоступен или токен не задан"
                if message.attempts >= OUTBOX_MAX_ATTEMPTS:
                    message.status = "failed"
                    logger.error(
                        "Outbox: сообщение #%s окончательно не доставлено vk_id=%s",
                        message.id,
                        message.vk_id,
                    )
                else:
                    logger.warning(
                        "Outbox: сообщение #%s пока не доставлено (попытка %s/%s)",
                        message.id,
                        message.attempts,
                        OUTBOX_MAX_ATTEMPTS,
                    )
        await session.commit()
    return delivered


async def outbox_worker_loop(interval: float | None = None) -> None:
    """Бесконечный цикл доставки outbox (запускается в event loop бота)."""
    delay = interval or OUTBOX_RETRY_DELAY_SECONDS
    while True:
        try:
            await deliver_pending_messages()
        except Exception:
            # Ни одна ошибка не должна ронять воркер
            logger.exception("Outbox worker: ошибка при доставке")
        await asyncio.sleep(delay)
