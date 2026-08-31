"""Тесты моделей данных (in-memory SQLite)."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.models import (
    Department,
    MessageAuthorType,
    Ticket,
    TicketMessage,
    TicketStatus,
    User,
    WebRole,
    WebUser,
)


async def test_create_user(db_session_maker):
    async with db_session_maker() as session:
        user = User(vk_id=100, full_name="Иван Иванов")
        session.add(user)
        await session.commit()

        loaded = await session.scalar(select(User).where(User.vk_id == 100))
        assert loaded is not None
        assert loaded.full_name == "Иван Иванов"


async def test_duplicate_user_vk_id_fails(db_session_maker):
    async with db_session_maker() as session:
        session.add(User(vk_id=200))
        await session.commit()

        session.add(User(vk_id=200))
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_create_ticket_with_defaults(db_session_maker):
    async with db_session_maker() as session:
        user = User(vk_id=300)
        department = Department(name="Жилбыт")
        session.add_all([user, department])
        await session.flush()

        ticket = Ticket(
            user_id=user.id,
            department_id=department.id,
            topic="Проблема",
            description="Описание проблемы",
        )
        session.add(ticket)
        await session.commit()

        loaded = await session.get(Ticket, ticket.id)
        assert loaded.status == TicketStatus.NEW
        assert loaded.is_anonymous is False
        assert loaded.auto_closed is False


async def test_anonymous_ticket(db_session_maker):
    async with db_session_maker() as session:
        ticket = Ticket(topic="Анонимная тема", is_anonymous=True, status=TicketStatus.ANONYMOUS)
        session.add(ticket)
        await session.commit()

        loaded = await session.get(Ticket, ticket.id)
        assert loaded.is_anonymous is True
        assert loaded.status == TicketStatus.ANONYMOUS


async def test_ticket_messages_history(db_session_maker):
    async with db_session_maker() as session:
        user = User(vk_id=400)
        session.add(user)
        await session.flush()

        ticket = Ticket(user_id=user.id, topic="Тема")
        session.add(ticket)
        await session.flush()

        session.add_all(
            [
                TicketMessage(
                    ticket_id=ticket.id,
                    author_type=MessageAuthorType.USER,
                    author_vk_id=400,
                    message="У меня проблема",
                ),
                TicketMessage(
                    ticket_id=ticket.id,
                    author_type=MessageAuthorType.ADMIN,
                    message="Принято в работу",
                ),
            ]
        )
        await session.commit()

        messages = (
            await session.scalars(
                select(TicketMessage)
                .where(TicketMessage.ticket_id == ticket.id)
                .order_by(TicketMessage.id)
            )
        ).all()
        assert len(messages) == 2
        assert messages[0].author_type == MessageAuthorType.USER
        assert messages[1].author_type == MessageAuthorType.ADMIN


async def test_web_user_roles(db_session_maker):
    async with db_session_maker() as session:
        web_user = WebUser(
            username="admin",
            password_hash="pbkdf2_sha256$100000$salt$hash",
            role=WebRole.SUPERADMIN,
        )
        session.add(web_user)
        await session.commit()

        loaded = await session.scalar(select(WebUser).where(WebUser.username == "admin"))
        assert loaded.role == WebRole.SUPERADMIN
        assert loaded.is_active is True
