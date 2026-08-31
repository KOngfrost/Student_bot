"""
Маршруты событий.

Безопасность:
- CSRF защищён middleware CSRFMiddleware в main.py
- IDOR: админ видит только события своего отдела (суперадмин — все)
- Санитизация входных данных от XSS
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime, timezone
import logging

from core.database import async_session_maker
from core.models import Event, Department, Admin, UserRole
from web.templating import templates
from web.security.middleware import sanitize_html

logger = logging.getLogger(__name__)

router = APIRouter()


def require_admin(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, detail="Redirect", headers={"Location": "/auth/login"})
    return user


@router.get("/")
async def events_page(request: Request, user=Depends(require_admin)):
    """Страница событий с IDOR-защитой."""
    from web.security.csrf import get_csrf_token

    events = []
    departments = []
    db_error = False

    try:
        async with async_session_maker() as session:
            depts_result = await session.execute(select(Department))
            departments = depts_result.scalars().all()

            admin_user_id = user.get("user_id")
            current_admin = await session.get(Admin, admin_user_id) if admin_user_id else None
            is_super = current_admin and current_admin.role == UserRole.SUPERADMIN
            dept_id = current_admin.department_id if current_admin else None

            if is_super:
                events_result = await session.execute(
                    select(Event)
                    .options(selectinload(Event.department), selectinload(Event.registrations))
                    .order_by(Event.event_date)
                )
            else:
                events_result = await session.execute(
                    select(Event)
                    .options(selectinload(Event.department), selectinload(Event.registrations))
                    .where(
                        (Event.department_id == dept_id) | (Event.department_id.is_(None))
                    )
                    .order_by(Event.event_date)
                )
            events = events_result.scalars().all()
    except Exception as e:
        db_error = True
        logger.error("Не удалось загрузить события: %s", e)

    return templates.TemplateResponse(
        "events.html",
        {
            "request": request,
            "user": user,
            "events": events,
            "departments": departments,
            "db_error": db_error,
            "active": "events",
            "success": request.session.pop("success", None),
            "error": request.session.pop("error", None),
            "csrf_token": get_csrf_token(request),
        }
    )


@router.post("/")
async def add_event(request: Request, user=Depends(require_admin)):
    """Создание события с санитизацией входных данных."""
    form = await request.form()
    department_id = int(form.get("department_id", 0))
    title = sanitize_html(form.get("title", ""))
    description = sanitize_html(form.get("description", ""))
    event_date_str = form.get("event_date", "")

    try:
        event_date = datetime.fromisoformat(event_date_str)
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=timezone.utc)

        async with async_session_maker() as session:
            event = Event(
                department_id=department_id,
                title=title,
                description=description or None,
                event_date=event_date,
            )
            session.add(event)
            await session.commit()
    except Exception as e:
        request.session["error"] = f"Ошибка: {e}"
        return RedirectResponse(url="/events/", status_code=302)

    request.session["success"] = "Событие создано"
    return RedirectResponse(url="/events/", status_code=302)


@router.post("/{event_id}/delete")
async def delete_event(request: Request, event_id: int, user=Depends(require_admin)):
    """Удаление события (POST с CSRF-токеном) с проверкой прав."""
    try:
        async with async_session_maker() as session:
            event = await session.get(Event, event_id)
            if not event:
                request.session["error"] = "Событие не найдено"
                return RedirectResponse(url="/events/", status_code=302)

            # Проверяем права
            admin_user_id = user.get("user_id")
            current_admin = await session.get(Admin, admin_user_id) if admin_user_id else None
            is_super = current_admin and current_admin.role == UserRole.SUPERADMIN
            dept_id = current_admin.department_id if current_admin else None

            if not is_super and event.department_id != dept_id:
                request.session["error"] = "Нет прав для удаления этого события"
                return RedirectResponse(url="/events/", status_code=302)

            await session.delete(event)
            await session.commit()
    except Exception as e:
        request.session["error"] = f"Ошибка: {e}"
        return RedirectResponse(url="/events/", status_code=302)

    request.session["success"] = "Событие удалено"
    return RedirectResponse(url="/events/", status_code=302)
