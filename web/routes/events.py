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
from core.models import Event, Department
from web.dependencies import get_admin_scope, require_auth, require_writer
from web.templating import templates
from web.security.middleware import sanitize_html

logger = logging.getLogger(__name__)

router = APIRouter()


require_admin = require_auth


@router.get("/")
async def events_page(request: Request, user=Depends(require_admin)):
    """Страница событий с IDOR-защитой."""
    from web.security.csrf import get_csrf_token

    events = []
    departments = []
    db_error = False

    try:
        async with async_session_maker() as session:
            is_super, dept_id = await get_admin_scope(session, user)
            depts_stmt = select(Department)
            if not is_super:
                depts_stmt = depts_stmt.where(Department.id == dept_id)
            depts_result = await session.execute(depts_stmt)
            departments = depts_result.scalars().all()

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
async def add_event(request: Request, user=Depends(require_writer)):
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
            is_super, dept_id = await get_admin_scope(session, user)
            if not is_super and dept_id != department_id:
                request.session["error"] = "Нет прав для работы с этим отделом"
                return RedirectResponse(url="/events/", status_code=302)
            event = Event(
                department_id=department_id,
                title=title,
                description=description or None,
                event_date=event_date,
            )
            session.add(event)
            await session.commit()
    except Exception:
        logger.exception("Не удалось создать событие")
        request.session["error"] = "Не удалось сохранить событие. Попробуйте позже."
        return RedirectResponse(url="/events/", status_code=302)

    request.session["success"] = "Событие создано"
    return RedirectResponse(url="/events/", status_code=302)


@router.post("/{event_id}/delete")
async def delete_event(request: Request, event_id: int, user=Depends(require_writer)):
    """Удаление события (POST с CSRF-токеном) с проверкой прав."""
    try:
        async with async_session_maker() as session:
            event = await session.get(Event, event_id)
            if not event:
                request.session["error"] = "Событие не найдено"
                return RedirectResponse(url="/events/", status_code=302)

            # Проверяем права
            is_super, dept_id = await get_admin_scope(session, user)

            if not is_super and event.department_id != dept_id:
                request.session["error"] = "Нет прав для удаления этого события"
                return RedirectResponse(url="/events/", status_code=302)

            await session.delete(event)
            await session.commit()
    except Exception:
        logger.exception("Не удалось удалить событие")
        request.session["error"] = "Не удалось удалить событие. Попробуйте позже."
        return RedirectResponse(url="/events/", status_code=302)

    request.session["success"] = "Событие удалено"
    return RedirectResponse(url="/events/", status_code=302)
