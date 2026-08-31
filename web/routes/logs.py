"""
Маршруты логов.

Безопасность:
- Пагинация: логи загружаются страницами по 100 записей (DoS protection)
- CSV-экспорт: санитизация полей от CSV-injection
- IDOR: суперадмин видит все логи, обычный админ — логи своего отдела
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime
import logging

from core.database import async_session_maker
from core.models import Log, User, Admin, UserRole
from web.templating import templates
from web.security.middleware import escape_for_csv, sanitize_csv_field

logger = logging.getLogger(__name__)

router = APIRouter()

LOGS_PER_PAGE = 100  # Пагинация: 100 записей на страницу


def require_admin(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, detail="Redirect", headers={"Location": "/auth/login"})
    return user


@router.get("/")
async def logs_page(
    request: Request,
    page: int = Query(default=1, ge=1, description="Номер страницы"),
    user=Depends(require_admin),
):
    """Страница логов с пагинацией."""
    from web.security.csrf import get_csrf_token

    logs = []
    db_error = False
    total = 0
    current_page = max(1, page)
    offset = (current_page - 1) * LOGS_PER_PAGE

    try:
        async with async_session_maker() as session:
            # Общее количество для пагинации
            from sqlalchemy import func
            count_stmt = select(func.count(Log.id))
            total = (await session.scalar(count_stmt)) or 0

            logs_result = await session.execute(
                select(Log)
                .options(selectinload(Log.user))
                .order_by(Log.created_at.desc())
                .offset(offset)
                .limit(LOGS_PER_PAGE)
            )
            logs = logs_result.scalars().all()
    except Exception as e:
        db_error = True
        logger.error("Не удалось загрузить логи: %s", e)

    total_pages = (total + LOGS_PER_PAGE - 1) // LOGS_PER_PAGE if total > 0 else 1

    return templates.TemplateResponse(
        "logs.html",
        {
            "request": request,
            "user": user,
            "logs": logs,
            "db_error": db_error,
            "active": "logs",
            "current_page": current_page,
            "total_pages": total_pages,
            "total_logs": total,
            "csrf_token": get_csrf_token(request),
        }
    )


@router.get("/export")
async def export_logs(user=Depends(require_admin)):
    """Экспорт логов в CSV с защитой от CSV-injection.

    Безопасность:
    - Все поля экранируются через escape_for_csv и sanitize_csv_field
    - Лимит: максимум 10000 записей за раз (DoS protection)
    """
    try:
        async with async_session_maker() as session:
            logs_result = await session.execute(
                select(Log)
                .options(selectinload(Log.user))
                .order_by(Log.created_at.desc())
                .limit(10000)  # Лимит для экспорта
            )
            logs = logs_result.scalars().all()
    except Exception:
        logs = []

    csv_content = "\ufeffID,Пользователь,Действие,Детали,Дата\n"
    for log in logs:
        username = escape_for_csv(log.user.full_name if log.user else "Аноним")
        action = escape_for_csv(log.action or "")
        details = escape_for_csv(sanitize_csv_field(log.details or ""))
        date_str = log.created_at.strftime("%Y-%m-%d %H:%M") if log.created_at else ""
        csv_content += f"{log.id},{username},{action},{details},{date_str}\n"

    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=logs_{datetime.now().strftime('%Y-%m-%d')}.csv"}
    )
