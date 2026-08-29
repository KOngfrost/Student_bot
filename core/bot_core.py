from sqlalchemy import func, select

from core.config import settings
from core.database import async_session_maker
from core.models import Admin, Ticket, User


class BotCore:
    @staticmethod
    async def get_or_create_user(vk_id: int) -> User:
        async with async_session_maker() as session:
            db_user = await session.scalar(
                select(User).where(User.vk_id == vk_id)
            )
            if db_user is None:
                db_user = User(vk_id=vk_id)
                session.add(db_user)
                await session.commit()
                await session.refresh(db_user)
            return db_user

    @staticmethod
    def is_admin_vk_id(vk_id: int | None) -> bool:
        return vk_id in settings.ADMIN_VK_IDS

    @staticmethod
    async def is_admin(user: User) -> bool:
        if user.vk_id is None:
            return False
        if BotCore.is_admin_vk_id(user.vk_id):
            return True
        async with async_session_maker() as session:
            admin = await session.scalar(
                select(Admin)
                .join(User, Admin.user_id == User.id)
                .where(User.vk_id == user.vk_id)
            )
            return admin is not None

    @staticmethod
    async def get_users() -> list[User]:
        async with async_session_maker() as session:
            result = await session.scalars(select(User).order_by(User.id))
            return list(result)

    @staticmethod
    async def get_user_tickets_count(user: User) -> int:
        if user.vk_id is None:
            return 0
        async with async_session_maker() as session:
            count = await session.scalar(
                select(func.count(Ticket.id))
                .join(User, Ticket.user_id == User.id)
                .where(User.vk_id == user.vk_id)
                .where(Ticket.status.not_in(("COMPLETED", "COMPLETED_AUTO")))
            )
            return int(count or 0)