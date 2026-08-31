"""
Маршруты заявок.

Безопасность:
- CSRF защищён middleware CSRFMiddleware в main.py
- IDOR: админ видит только заявки своего отдела (суперадмин — все)
- API-эндпоинты также проверяют права доступа
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import logging

from core.database import async_session_maker
from core.models import Ticket, Department, Admin, UserRole
from web.templating import templates
from web.security.csrf import get_csrf_token

logger = logging.getLogger(__name__)

router = APIRouter()


def require_admin(request: Request) -> dict:
    """Депенденция для проверки прав админа."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, detail="Redirect", headers={"Location": "/auth/login"})
    return user


def _get_admin_dept_filter(session, user: dict):
    """
    Получить фильтр отдела для текущего админа.
    Возвращает (is_super, dept_id).
    """
    admin_user_id = user.get("user_id")
    if not admin_user_id:
        return False, None
    current_admin = session.get(Admin, admin_user_id)
    is_super = current_admin and current_admin.role == UserRole.SUPERADMIN
    dept_id = current_admin.department_id if current_admin else None
    return is_super, dept_id


@router.get("/")
async def tickets_page(request: Request, user=Depends(require_admin)):
    """Страница заявок с IDOR-защитой."""
    tickets = []
    departments = []
    db_error = False

    try:
        async with async_session_maker() as session:
            tickets_result = await session.execute(
                select(Ticket)
                .options(selectinload(Ticket.user), selectinload(Ticket.department))
                .order_by(Ticket.created_at.desc())
            )
            tickets = tickets_result.scalars().all()

            depts_result = await session.execute(select(Department))
            departments = depts_result.scalars().all()
    except Exception as e:
        db_error = True
        logger.error("Не удалось загрузить заявки: %s", e)

    return templates.TemplateResponse(
        "tickets.html",
        {
            "request": request,
            "user": user,
            "tickets": tickets,
            "departments": departments,
            "db_error": db_error,
            "active": "tickets",
            "csrf_token": get_csrf_token(request),
        }
    )


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: int, user=Depends(require_admin)):
    """Получение данных заявки для модального окна (JSON) с проверкой прав."""
    try:
        async with async_session_maker() as session:
            ticket = await session.scalar(
                select(Ticket)
                .options(selectinload(Ticket.user), selectinload(Ticket.department))
                .where(Ticket.id == ticket_id)
            )
            if not ticket:
                raise HTTPException(status_code=404, detail="Заявка не найдена")

            # IDOR-проверка: админ видит только заявки своего отдела
            is_super, dept_id = _get_admin_dept_filter(session, user)
            if not is_super and ticket.department_id != dept_id:
                raise HTTPException(status_code=403, detail="Нет прав для просмотра этой заявки")

            return {
                "id": ticket.id,
                "topic": ticket.topic,
                "description": ticket.description,
                "status": {"value": ticket.status.value},
                "is_anonymous": ticket.is_anonymous,
                "auto_closed": ticket.auto_closed,
                "response_text": ticket.response_text,
                "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
                "user": {
                    "full_name": ticket.user.full_name if ticket.user else None,
                    "dormitory": ticket.user.dormitory if ticket.user else None,
                } if ticket.user else None,
                "department": {
                    "name": ticket.department.name if ticket.department else None,
                } if ticket.department else None,
            }
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="Ошибка при загрузке данных")
