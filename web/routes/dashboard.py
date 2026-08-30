from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from core.database import async_session_maker
from core.models import Ticket, Department, TicketStatus
from web.templating import templates

router = APIRouter()


def require_admin(request: Request) -> dict:
    """Депенденция для проверки прав админа."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, detail="Redirect", headers={"Location": "/auth/login"})
    return user


@router.get("/")
async def dashboard(request: Request, user=Depends(require_admin)):
    """Главная страница дашборда."""
    try:
        async with async_session_maker() as session:
            # Статистика
            total_tickets = await session.scalar(select(func.count(Ticket.id))) or 0
            in_progress = await session.scalar(
                select(func.count(Ticket.id)).where(Ticket.status == TicketStatus.IN_PROGRESS)
            ) or 0
            completed = await session.scalar(
                select(func.count(Ticket.id)).where(
                    Ticket.status.in_([TicketStatus.COMPLETED, TicketStatus.COMPLETED_AUTO])
                )
            ) or 0
            new_tickets = await session.scalar(
                select(func.count(Ticket.id)).where(Ticket.status == TicketStatus.NEW)
            ) or 0
            
            # Последние заявки
            recent_result = await session.execute(
                select(Ticket)
                .options(selectinload(Ticket.user), selectinload(Ticket.department))
                .order_by(Ticket.created_at.desc())
                .limit(10)
            )
            recent_tickets = recent_result.scalars().all()
    except Exception as e:
        # Если БД недоступна, показываем пустые данные
        recent_tickets = []
        total_tickets = 0
        in_progress = 0
        completed = 0
        new_tickets = 0
    
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
            "active": "dashboard",
        }
    )
