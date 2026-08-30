from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import logging

from core.database import async_session_maker
from core.models import User, Admin, Department, UserRole
from web.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


def require_admin(request: Request) -> dict:
    """Депенденция для проверки прав админа."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, detail="Redirect", headers={"Location": "/auth/login"})
    return user


@router.get("/")
async def admins_page(request: Request, user=Depends(require_admin)):
    """Страница управления администраторами."""
    admins = []
    departments = []
    db_error = False
    try:
        async with async_session_maker() as session:
            admins_result = await session.execute(
                select(Admin)
                .options(selectinload(Admin.user), selectinload(Admin.department))
                .order_by(Admin.id)
            )
            admins = admins_result.scalars().all()
            
            depts_result = await session.execute(select(Department))
            departments = depts_result.scalars().all()
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
        }
    )


@router.post("/")
async def add_admin(request: Request, user=Depends(require_admin)):
    """Добавление нового администратора."""
    form = await request.form()
    vk_id = int(form.get("vk_id", 0))
    full_name = form.get("full_name", "")
    department_id = form.get("department_id")
    role = form.get("role", "admin")
    
    try:
        async with async_session_maker() as session:
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
    except Exception as e:
        request.session["error"] = f"Ошибка: {e}"
        return RedirectResponse(url="/admin/admins/", status_code=302)
    
    request.session["success"] = "Администратор успешно добавлен"
    return RedirectResponse(url="/admin/admins/", status_code=302)


@router.get("/{admin_id}/delete")
async def delete_admin(request: Request, admin_id: int, user=Depends(require_admin)):
    """Удаление администратора."""
    try:
        async with async_session_maker() as session:
            admin = await session.get(Admin, admin_id)
            if not admin:
                request.session["error"] = "Администратор не найден"
                return RedirectResponse(url="/admin/admins/", status_code=302)
            
            if admin.role == UserRole.SUPERADMIN:
                request.session["error"] = "Нельзя удалить суперадмина"
                return RedirectResponse(url="/admin/admins/", status_code=302)
            
            await session.delete(admin)
            await session.commit()
    except Exception as e:
        request.session["error"] = f"Ошибка: {e}"
        return RedirectResponse(url="/admin/admins/", status_code=302)
    
    request.session["success"] = "Администратор удалён"
    return RedirectResponse(url="/admin/admins/", status_code=302)
