"""
Маршруты управления администраторами.

Безопасность:
- CSRF защищён middleware CSRFMiddleware в main.py
- require_admin проверяет сессию + роль (суперадмин/админ)
- IDOR: админ видит только своих подчинённых (суперадмин видит всех)
- Добавление суперадминов: только текущий суперадмин может назначать новых
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
import logging

from core.database import async_session_maker
from core.models import User, Admin, Department, UserRole
from web.dependencies import is_superadmin, require_auth as require_authenticated
from web.dependencies import require_superadmin as require_superadmin_dependency
from web.routes.auth import require_crud_rate_limit
from web.templating import templates
from web.security.csrf import get_csrf_token
from web.security.middleware import sanitize_html

logger = logging.getLogger(__name__)

router = APIRouter()


async def require_admin(request: Request) -> dict:
    """Депенденция для проверки актуальной авторизации админа."""
    return await require_authenticated(request)


async def require_superadmin(request: Request) -> dict:
    return await require_superadmin_dependency(request)


@router.get("/")
async def admins_page(request: Request, user=Depends(require_admin)):
    """Страница управления администраторами.

    IDOR-защита:
    - Суперадмин видит всех админов.
    - Обычный админ видит только тех, кто привязан к его отделу (или не привязан к отделу).
    """
    admins = []
    departments = []
    db_error = False

    try:
        async with async_session_maker() as session:
            depts_result = await session.execute(select(Department))
            departments = depts_result.scalars().all()

            if is_superadmin(user):
                # Суперадмин видит всех
                admins_result = await session.execute(
                    select(Admin)
                    .options(selectinload(Admin.user), selectinload(Admin.department))
                    .order_by(Admin.id)
                )
                admins = admins_result.scalars().all()
            else:
                # Обычный админ видит только:
                # 1. Админов своего отдела
                # 2. Админов без привязки к отделу
                dept_id = user.get("department_id")
                admins_result = await session.execute(
                    select(Admin)
                    .options(selectinload(Admin.user), selectinload(Admin.department))
                    .where(
                        (Admin.department_id == dept_id) | (Admin.department_id.is_(None))
                    )
                    .order_by(Admin.id)
                )
                admins = admins_result.scalars().all()
    except Exception as e:
        db_error = True
        logger.error("Не удалось загрузить администраторов: %s", e)

    return templates.TemplateResponse(
        "admins.html",
        {
            "request": request,
            "user": user,
            "admins": admins,
            "departments": departments,
            "db_error": db_error,
            "active": "admins",
            "success": request.session.pop("success", None),
            "error": request.session.pop("error", None),
            "csrf_token": get_csrf_token(request),
        }
    )


@router.post("/")
async def add_admin(request: Request, user=Depends(require_admin)):
    """Добавление нового администратора.

    Безопасность:
    - CSRF: защищён middleware CSRFMiddleware (токен из сессии)
    - Rate limiting: не более 20 запросов на IP за 5 минут
    - Только суперадмин может назначать роль superadmin
    - Обычный админ может назначать только роль admin
    - Данные из форм санитизируются
    """
    require_crud_rate_limit(request)
    form = await request.form()
    vk_id = int(form.get("vk_id", 0))
    full_name = sanitize_html(form.get("full_name", ""))
    department_id = form.get("department_id")
    role = form.get("role", "admin")

    # Проверка прав: только суперадмин может назначать роль superadmin
    try:
        async with async_session_maker() as session:
            if role == "superadmin" and not is_superadmin(user):
                request.session["error"] = "Только суперадмин может назначать суперадминов"
                return RedirectResponse(url="/admin/admins/", status_code=302)

            # Обычный админ может назначать только роль admin
            if role == "admin" and not is_superadmin(user):
                request.session["error"] = "Недостаточно прав для назначения администратора"
                return RedirectResponse(url="/admin/admins/", status_code=302)

            # Получаем или создаём пользователя
            db_user = await session.scalar(select(User).where(User.vk_id == vk_id))
            if not db_user:
                db_user = User(vk_id=vk_id, full_name=full_name or None)
                session.add(db_user)
                await session.commit()
                await session.refresh(db_user)
            elif full_name:
                db_user.full_name = full_name
                await session.commit()

            # Проверяем, нет ли уже такого админа
            existing = await session.scalar(
                select(Admin).where(Admin.user_id == db_user.id)
            )
            if existing:
                request.session["error"] = "Этот пользователь уже является админом"
                return RedirectResponse(url="/admin/admins/", status_code=302)

            # Создаём запись админа
            new_admin = Admin(
                user_id=db_user.id,
                department_id=int(department_id) if department_id else None,
                role=UserRole(role),
            )
            session.add(new_admin)
            await session.commit()
    except Exception:
        logger.exception("Не удалось добавить администратора")
        request.session["error"] = "Не удалось сохранить изменения. Попробуйте позже."
        return RedirectResponse(url="/admin/admins/", status_code=302)

    request.session["success"] = "Администратор успешно добавлен"
    return RedirectResponse(url="/admin/admins/", status_code=302)


@router.post("/{admin_id}/delete")
async def delete_admin(request: Request, admin_id: int, user=Depends(require_admin)):
    """Удаление администратора (POST с CSRF-токеном и подтверждением).

    Безопасность:
    - Rate limiting: не более 20 запросов на IP за 5 минут
    - Только суперадмин может удалять администраторов
    - Нельзя удалить самого себя или последнего суперадмина
    """
    require_crud_rate_limit(request)
    if not is_superadmin(user):
        request.session["error"] = "Только суперадмин может удалять администраторов"
        return RedirectResponse(url="/admin/admins/", status_code=302)

    try:
        async with async_session_maker() as session:
            admin = await session.get(Admin, admin_id)
            if not admin:
                request.session["error"] = "Администратор не найден"
                return RedirectResponse(url="/admin/admins/", status_code=302)

            # Нельзя удалить самого себя (для legacy-админов с user_id в сессии)
            if user.get("user_id") == admin.id:
                request.session["error"] = "Нельзя удалить себя"
                return RedirectResponse(url="/admin/admins/", status_code=302)

            if admin.role == UserRole.SUPERADMIN:
                superadmin_count = await session.scalar(
                    select(func.count(Admin.id)).where(Admin.role == UserRole.SUPERADMIN)
                )
                if superadmin_count <= 1:
                    request.session["error"] = "Нельзя удалить последнего суперадмина"
                    return RedirectResponse(url="/admin/admins/", status_code=302)

            await session.delete(admin)
            await session.commit()
    except Exception:
        logger.exception("Не удалось удалить администратора")
        request.session["error"] = "Не удалось удалить администратора. Попробуйте позже."
        return RedirectResponse(url="/admin/admins/", status_code=302)

    request.session["success"] = "Администратор удалён"
    return RedirectResponse(url="/admin/admins/", status_code=302)
