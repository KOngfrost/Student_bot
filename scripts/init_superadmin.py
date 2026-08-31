#!/usr/bin/env python3
"""
Скрипт для инициализации первого суперадмина.
Запустить один раз при первом запуске веб-админки.

Пример:
    python scripts/init_superadmin.py --vk-id 193626953 --name "Иванов Иван"
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в sys.path для импорта модулей
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import async_session_maker
from core.models import Admin, User, UserRole


async def init_superadmin(vk_id: int, full_name: str = ""):
    """Создаёт первого суперадмина в базе данных."""
    async with async_session_maker() as session:
        # Проверяем, есть ли уже суперадмины
        superadmins = await session.execute(
            select(Admin)
            .options(selectinload(Admin.user))
            .where(Admin.role == UserRole.SUPERADMIN)
        )
        existing_superadmins = superadmins.scalars().all()
        
        if existing_superadmins:
            print(f"⚠️  Уже есть {len(existing_superadmins)} суперадмин(ов)")
            for admin in existing_superadmins:
                print(f"   - {admin.user.full_name or 'Без имени'} (VK: {admin.user.vk_id})")
            return
        
        # Получаем или создаём пользователя
        user = await session.execute(
            select(User).where(User.vk_id == vk_id)
        )
        user = user.scalar_one_or_none()
        
        if not user:
            user = User(vk_id=vk_id, full_name=full_name or None)
            session.add(user)
            await session.flush()
            print(f"✅ Создан пользователь: {full_name or f'VK:{vk_id}'}")
        else:
            if full_name and not user.full_name:
                user.full_name = full_name
                print(f"✅ Обновлено имя: {full_name}")
            else:
                print(f"ℹ️  Пользователь уже существует: {user.full_name or vk_id}")
        
        # Создаём суперадмина
        admin = Admin(
            user_id=user.id,
            department_id=None,
            role=UserRole.SUPERADMIN,
        )
        session.add(admin)
        await session.commit()
        
        print("\n🎉 Суперадмин успешно создан!")
        print(f"   Имя: {full_name or 'Не указано'}")
        print(f"   VK ID: {vk_id}")
        print("\n📝 Для входа в веб-админку задайте в .env:")
        print("   WEB_ADMIN_USERNAME=<ваш логин>")
        print("   WEB_ADMIN_PASSWORD=<ваш пароль>")


def main():
    parser = argparse.ArgumentParser(description="Инициализация суперадмина")
    parser.add_argument("--vk-id", type=int, required=True, help="VK ID пользователя")
    parser.add_argument("--name", type=str, default="", help="ФИО пользователя")
    args = parser.parse_args()
    
    try:
        asyncio.run(init_superadmin(args.vk_id, args.name))
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
