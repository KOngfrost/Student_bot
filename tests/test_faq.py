"""Тесты FAQ: ограничения целостности и дефолты."""

import pytest
from sqlalchemy.exc import IntegrityError

from core.models import Department, FAQNode


async def test_faq_final_node_requires_answer(db_session_maker):
    async with db_session_maker() as session:
        department = Department(name="Информ")
        session.add(department)
        await session.flush()

        node = FAQNode(
            department_id=department.id,
            question="Как заселиться?",
            is_final=True,
            final_answer=None,  # финальный узел без ответа запрещён
        )
        session.add(node)
        with pytest.raises(IntegrityError):
            await session.commit()


async def test_faq_final_node_with_answer_ok(db_session_maker):
    async with db_session_maker() as session:
        department = Department(name="Информ")
        session.add(department)
        await session.flush()

        node = FAQNode(
            department_id=department.id,
            question="Как заселиться?",
            is_final=True,
            final_answer="Обратитесь в пропускной пункт",
        )
        session.add(node)
        await session.commit()

        await session.refresh(node)
        assert node.is_final is True
        assert node.final_answer == "Обратитесь в пропускной пункт"


async def test_faq_intermediate_node_without_answer_ok(db_session_maker):
    async with db_session_maker() as session:
        department = Department(name="Жилбыт")
        session.add(department)
        await session.flush()

        node = FAQNode(
            department_id=department.id,
            question="Выберите тему:",
            is_final=False,
        )
        session.add(node)
        await session.commit()

        await session.refresh(node)
        assert node.is_final is False
        assert node.order_index == 0
