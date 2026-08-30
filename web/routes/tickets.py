from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import async_session_maker
from core.models import Ticket, Department
from web.templating import templates

router = APIRouter()


def require_admin(request: Request) -> dict:
    """Депенденция для проверки прав админа."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, detail="Redirect", headers={"Location": "/auth/login"})
    return user


@router.get("/")
async def tickets_page(request: Request, user=Depends(require_admin)):
    """Страница заявок."""
    tickets = []
    departments = []
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
    except Exception:
        pass
    
    return templates.TemplateResponse(
        "tickets.html",
        {
            "request": request,
            "user": user,
            "tickets": tickets,
            "departments": departments,
            "active": "tickets",
        }
    )


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: int, user=Depends(require_admin)):
    """Получение данных заявки для модального окна (JSON)."""
    try:
        async with async_session_maker() as session:
            # selectinload обязателен: в async-сессии lazy-загрузка связей
            # вызывает MissingGreenlet
            ticket = await session.scalar(
                select(Ticket)
                .options(selectinload(Ticket.user), selectinload(Ticket.department))
                .where(Ticket.id == ticket_id)
            )
            if not ticket:
                raise HTTPException(status_code=404, detail="Заявка не найдена")
            
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
