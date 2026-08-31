"""
Маршруты дашборда.

Безопасность:
- IDOR: админ видит только статистику своего отдела (суперадмин — все)
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
import logging

from core.database import async_session_maker
from core.models import Ticket, Department, TicketStatus, Admin, UserRole
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


@router.get("/")
async def dashboard(request: Request, user=Depends(require_admin)):
    """Главная страница дашборда с IDOR-защитой."""
    db_error = False

    try:
        async with async_session_maker() as session:
            # Проверяем роль текущего админа
            admin_user_id = user.get("user_id")
            current_admin = await session.get(Admin, admin_user_id) if admin_user_id else None
            is_super = current_admin and current_admin.role == UserRole.SUPERADMIN
            dept_id = current_admin.department_id if current_admin else None

            # Фильтруем запросы по отделу
            dept_filter = None if is_super else dept_id

            # Статистика
            stmt = select(func.count(Ticket.id))
            if dept_filter is not None:
                stmt = stmt.where(Ticket.department_id == dept_filter)
            total_tickets = await session.scalar(stmt) or 0

            stmt = select(func.count(Ticket.id)).where(Ticket.status == TicketStatus.IN_PROGRESS)
            if dept_filter is not None:
                stmt = stmt.where(Ticket.department_id == dept_filter)
            in_progress = await session.scalar(stmt) or 0

            stmt = select(func.count(Ticket.id)).where(
                Ticket.status.in_([TicketStatus.COMPLETED, TicketStatus.COMPLETED_AUTO])
            )
            if dept_filter is not None:
                stmt = stmt.where(Ticket.department_id == dept_filter)
            completed = await session.scalar(stmt) or 0

            stmt = select(func.count(Ticket.id)).where(Ticket.status == TicketStatus.NEW)
            if dept_filter is not None:
                stmt = stmt.where(Ticket.department_id == dept_filter)
            new_tickets = await session.scalar(stmt) or 0

            # Последние заявки
            recent_result = await session.execute(
                select(Ticket)
                .options(selectinload(Ticket.user), selectinload(Ticket.department))
                .order_by(Ticket.created_at.desc())
                .limit(10)
            )
            recent_tickets = recent_result.scalars().all()
    except Exception as e:
        logger.error("Не удалось загрузить статистику: %s", e)
        recent_tickets = []
        total_tickets = 0
        in_progress = 0
        completed = 0
        new_tickets = 0
        db_error = True

    stats = {
        "total_tickets": total_tickets,
        "in_progress": in_progress,
        "completed": completed,
        "new_tickets": new_tickets,
    }

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": user,
            "stats": stats,
            "recent_tickets": recent_tickets,
            "db_error": db_error,
            "active": "dashboard",
            "csrf_token": get_csrf_token(request),
        }
    )
