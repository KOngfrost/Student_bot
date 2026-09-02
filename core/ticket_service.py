"""Сервис заявок: единая бизнес-логика для VK-бота и веб-панели.

Используется:
- VK-ботом: просмотр «Мои заявки», история переписки.
- Веб-панелью: ответ администратора, смена статуса, назначение отдела.

Все функции принимают/создают AsyncSession и работают через SQLAlchemy-модели.
"""

import logging
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database import async_session_maker
from core.models import (
    Department,
    Log,
    MessageAuthorType,
    Ticket,
    TicketMessage,
    TicketStatus,
    User,
)
from core.outbox import add_outbox_message, fire_outbox_delivery

logger = logging.getLogger(__name__)

# === Общий контекстный менеджер для транзакций ===


@asynccontextmanager
async def ticket_transaction():
    """Контекстный менеджер для работы с транзакциями заявок.

    Позволяет объединять несколько операций в одну транзакцию:

        async with ticket_transaction() as session:
            ticket = await session.get(Ticket, 123)
            await session.execute(...)  # другие операции
            # commit() вызывается автоматически при выходе из контекста

    Также можно вызывать несколько раз вложенно — сессия будет общая.
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# === Остальной код ===

# Допустимые переходы статусов заявки:
# NEW -> IN_PROGRESS -> TRANSFERRED_ADMIN/HOUSEKEEPING -> COMPLETED -> COMPLETED_AUTO
ALLOWED_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.NEW: {
        TicketStatus.IN_PROGRESS,
        TicketStatus.TRANSFERRED_ADMIN,
        TicketStatus.TRANSFERRED_HOUSEKEEPING,
        TicketStatus.COMPLETED,
    },
    TicketStatus.IN_PROGRESS: {
        TicketStatus.TRANSFERRED_ADMIN,
        TicketStatus.TRANSFERRED_HOUSEKEEPING,
        TicketStatus.COMPLETED,
    },
    TicketStatus.TRANSFERRED_ADMIN: {
        TicketStatus.IN_PROGRESS,
        TicketStatus.COMPLETED,
    },
    TicketStatus.TRANSFERRED_HOUSEKEEPING: {
        TicketStatus.IN_PROGRESS,
        TicketStatus.COMPLETED,
    },
    TicketStatus.COMPLETED: {TicketStatus.COMPLETED_AUTO},
    TicketStatus.COMPLETED_AUTO: set(),
    TicketStatus.ANONYMOUS: {
        TicketStatus.IN_PROGRESS,
        TicketStatus.TRANSFERRED_ADMIN,
        TicketStatus.TRANSFERRED_HOUSEKEEPING,
        TicketStatus.COMPLETED,
    },
}

COMPLETED_STATUSES = {TicketStatus.COMPLETED, TicketStatus.COMPLETED_AUTO}


class StatusTransitionError(ValueError):
    """Недопустимый переход статуса заявки."""


def can_transition(current: TicketStatus, new: TicketStatus) -> bool:
    """Проверить, допустим ли переход статуса."""
    return new in ALLOWED_TRANSITIONS.get(current, set())


def validate_transition(current: TicketStatus, new: TicketStatus) -> None:
    """Выбросить StatusTransitionError, если переход недопустим."""
    if current == new:
        return
    if not can_transition(current, new):
        raise StatusTransitionError(
            f"Недопустимый переход статуса: {current.value} -> {new.value}"
        )


async def get_user_tickets(
    vk_id: int,
    include_completed: bool = False,
    limit: int = 10,
    offset: int = 0,
) -> list[Ticket]:
    """Получить заявки пользователя по его VK ID (новые сверху).

    limit/offset дают пагинацию в боте («Показать ещё») и веб-панели.
    """
    async with async_session_maker() as session:
        stmt = (
            select(Ticket)
            .join(User, Ticket.user_id == User.id)
            .options(selectinload(Ticket.department), selectinload(Ticket.user))
            .where(User.vk_id == vk_id)
            .order_by(Ticket.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if not include_completed:
            stmt = stmt.where(Ticket.status.not_in(tuple(COMPLETED_STATUSES)))
        result = await session.scalars(stmt)
        return list(result)


async def get_ticket_messages(ticket_id: int) -> list[TicketMessage]:
    """Получить историю переписки по заявке."""
    async with async_session_maker() as session:
        result = await session.scalars(
            select(TicketMessage)
            .where(TicketMessage.ticket_id == ticket_id)
            .order_by(TicketMessage.created_at)
        )
        return list(result)


def add_ticket_message(
    session: AsyncSession,
    ticket: Ticket,
    author_type: MessageAuthorType,
    message: str,
    author_vk_id: int | None = None,
) -> TicketMessage:
    """Добавить сообщение в историю заявки (без commit — вызывает вызывающий код)."""
    entry = TicketMessage(
        ticket_id=ticket.id,
        author_type=author_type,
        author_vk_id=author_vk_id,
        message=message,
    )
    session.add(entry)
    return entry


async def reply_to_ticket(
    ticket_id: int,
    admin_username: str,
    message: str,
    complete: bool = False,
) -> tuple[Ticket | None, bool]:
    """Ответ администратора на заявку из веб-панели.

    Шаги (outbox-паттерн, устраняет потерю уведомлений):
    1. Открыть транзакцию, заблокировать строку заявки (FOR UPDATE),
       исключая конкурентное редактирование другими админами.
    2. Сохранить сообщение в ticket_messages, обновить статус, записать Log
       и положить VK-уведомление в таблицу vk_outbox — всё в ОДНОЙ транзакции.
    3. commit() — только после этого сообщение доставляется фоновым воркером
       (с повтором попыток), поэтому «ответ в VK без записи в БД» невозможен.

    Возвращает (заявка, запланирована_ли_доставка_в_VK) или (None, False),
    если заявка не найдена.
    """
    async with ticket_transaction() as session:
        ticket = await session.scalar(
            select(Ticket)
            .options(selectinload(Ticket.user), selectinload(Ticket.department))
            .where(Ticket.id == ticket_id)
            .with_for_update()
        )
        if ticket is None:
            return None, False

        # 1. История
        add_ticket_message(session, ticket, MessageAuthorType.ADMIN, message)

        # 2. Итоговый ответ
        ticket.response_text = message

        # 3. Статус
        if complete and ticket.status not in COMPLETED_STATUSES:
            validate_transition(ticket.status, TicketStatus.COMPLETED)
            ticket.status = TicketStatus.COMPLETED
        elif ticket.status == TicketStatus.NEW:
            ticket.status = TicketStatus.IN_PROGRESS

        # 4. Журнал
        session.add(
            Log(
                user_id=ticket.user_id,
                action="web_reply",
                details=(
                    f"Администратор {admin_username} ответил на заявку #{ticket.id}"
                    f" (статус: {ticket.status.value})"
                ),
            )
        )

        # 5. Откладываем VK-уведомление в ту же транзакцию (outbox)
        scheduled = False
        if not ticket.is_anonymous and ticket.user and ticket.user.vk_id:
            add_outbox_message(
                session,
                ticket.user.vk_id,
                (
                    f"Ответ на вашу заявку #{ticket.id} "
                    f"({ticket.department.name if ticket.department else '—'}):\n\n{message}"
                ),
            )
            scheduled = True

    # commit() уже вызван внутри ticket_transaction
    if scheduled:
        fire_outbox_delivery()

    return ticket, scheduled


async def change_ticket_status(
    ticket_id: int,
    new_status: TicketStatus,
    admin_username: str,
) -> Ticket | None:
    """Сменить статус заявки с проверкой допустимых переходов. Пишет действие в logs.

    Строка заявки блокируется (SELECT...FOR UPDATE), чтобы два администратора
    не могли одновременно изменить статус одной заявки.
    """
    async with ticket_transaction() as session:
        ticket = await session.scalar(
            select(Ticket).where(Ticket.id == ticket_id).with_for_update()
        )
        if ticket is None:
            return None

        validate_transition(ticket.status, new_status)
        old_status = ticket.status
        ticket.status = new_status

        add_ticket_message(
            session,
            ticket,
            MessageAuthorType.SYSTEM,
            f"Статус изменён: {old_status.value} -> {new_status.value} (администратор {admin_username})",
        )
        session.add(
            Log(
                user_id=ticket.user_id,
                action="web_status_change",
                details=(
                    f"Администратор {admin_username} изменил статус заявки "
                    f"#{ticket.id}: {old_status.value} -> {new_status.value}"
                ),
            )
        )
        return ticket


async def assign_ticket_department(
    ticket_id: int,
    department_id: int,
    admin_username: str,
) -> Ticket | None:
    """Переназначить заявку другому отделу (только суперадмин). Пишет действие в logs.

    Строка заявки блокируется (SELECT...FOR UPDATE) для защиты от
    конкурентной передачи в разные отделы.
    """
    async with ticket_transaction() as session:
        ticket = await session.scalar(
            select(Ticket)
            .options(selectinload(Ticket.department), selectinload(Ticket.user))
            .where(Ticket.id == ticket_id)
            .with_for_update()
        )
        department = await session.get(Department, department_id)
        if ticket is None or department is None:
            return None

        old_department = ticket.department.name if ticket.department else "—"
        ticket.department_id = department_id

        add_ticket_message(
            session,
            ticket,
            MessageAuthorType.SYSTEM,
            f"Заявка передана из отдела «{old_department}» в отдел «{department.name}» "
            f"(администратор {admin_username})",
        )
        session.add(
            Log(
                user_id=ticket.user_id,
                action="web_assign",
                details=(
                    f"Администратор {admin_username} передал заявку #{ticket.id} "
                    f"из «{old_department}» в «{department.name}»"
                ),
            )
        )
        return ticket


def format_ticket_list(tickets: list[Ticket]) -> str:
    """Список заявок для VK-сообщения: номер, отдел, тема, дата, статус, ответ."""
    if not tickets:
        return "У вас пока нет заявок."

    lines = ["Ваши заявки:", ""]
    for ticket in tickets:
        created = ticket.created_at.strftime("%d.%m.%Y") if ticket.created_at else "—"
        dept = ticket.department.name if ticket.department else "—"
        lines.append(f"#{ticket.id} · {dept} · {ticket.topic or 'Без темы'}")
        lines.append(f"   Статус: {ticket.status.value} · создана {created}")
        if ticket.response_text:
            preview = ticket.response_text[:120]
            lines.append(f"   Ответ: {preview}{'…' if len(ticket.response_text) > 120 else ''}")
        lines.append("")
    lines.append("Нажмите «Подробнее #N», чтобы увидеть историю заявки.")
    return "\n".join(lines)


def format_ticket_details(ticket: Ticket, messages: list[TicketMessage]) -> str:
    """Подробная карточка заявки с историей переписки."""
    created = ticket.created_at.strftime("%d.%m.%Y %H:%M") if ticket.created_at else "—"
    dept = ticket.department.name if ticket.department else "—"

    lines = [
        f"Заявка #{ticket.id}",
        f"Отдел: {dept}",
        f"Тема: {ticket.topic or 'Без темы'}",
        f"Статус: {ticket.status.value}",
        f"Создана: {created}",
        "",
        "История обращений:",
        "— — —",
    ]

    if not messages:
        lines.append(f"Вы: {ticket.description or '—'}")
        if ticket.response_text:
            lines.append(f"Администратор: {ticket.response_text}")
    else:
        for msg in messages:
            author = {
                MessageAuthorType.USER: "Вы",
                MessageAuthorType.ADMIN: "Администратор",
                MessageAuthorType.SYSTEM: "Система",
            }.get(msg.author_type, "—")
            when = msg.created_at.strftime("%d.%m.%Y %H:%M") if msg.created_at else ""
            lines.append(f"[{when}] {author}: {msg.message}")

    return "\n".join(lines)


def mask_anonymous_data(full_name: str | None, is_anonymous: bool) -> str:
    """Маскировка персональных данных анонимных заявок."""
    if is_anonymous:
        return "Аноним"
    return full_name or "—"


# === Создание анонимных заявок ===


async def create_anonymous_ticket(topic: str, description: str) -> Ticket:
    """Создать анонимную заявку (согласно ТЗ: user_id=NULL, department_id=NULL, статус=Анонимное).

    Только суперадмин видит такие заявки в веб-панели.

    Args:
        topic: Тема обращения.
        description: Текст обращения.

    Returns:
        Созданная заявка.
    """
    async with ticket_transaction() as session:
        ticket = Ticket(
            user_id=None,           # аноним
            department_id=None,     # без отдела
            topic=topic,
            description=description,
            status=TicketStatus.ANONYMOUS,
            is_anonymous=True,
            auto_closed=False,
        )
        session.add(ticket)
        await session.flush()  # получаем ticket.id

        # Добавляем сообщение в историю
        add_ticket_message(
            session,
            ticket,
            MessageAuthorType.USER,
            description,
            author_vk_id=None,  # аноним
        )

        # Журналируем создание
        session.add(
            Log(
                user_id=None,
                action="anonymous_ticket_created",
                details=f"Создана анонимная заявка #{ticket.id}: {topic}",
            )
        )

        return ticket
