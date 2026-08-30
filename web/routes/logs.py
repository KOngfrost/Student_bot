from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from datetime import datetime
import logging

from core.database import async_session_maker
from core.models import Log, User
from web.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()


def require_admin(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, detail="Redirect", headers={"Location": "/auth/login"})
    return user


@router.get("/")
async def logs_page(request: Request, user=Depends(require_admin)):
    logs = []
    db_error = False
    try:
        async with async_session_maker() as session:
            logs_result = await session.execute(
                select(Log)
                .options(selectinload(Log.user))
                .order_by(Log.created_at.desc())
                .limit(200)
            )
            logs = logs_result.scalars().all()
    except Exception as e:
        db_error = True
        logger.error("Не удалось загрузить логи: %s", e)
    
    return templates.TemplateResponse(
        "logs.html",
        {
            "request": request,
            "user": user,
            "logs": logs,
            "db_error": db_error,
            "active": "logs",
        }
    )


@router.get("/export")
async def export_logs(user=Depends(require_admin)):
    try:
        async with async_session_maker() as session:
            logs_result = await session.execute(
                select(Log)
                .options(selectinload(Log.user))
                .order_by(Log.created_at.desc())
            )
            logs = logs_result.scalars().all()
    except Exception:
        logs = []
    
    csv_content = "\ufeffID,Пользователь,Действие,Детали,Дата\n"
    for log in logs:
        username = log.user.full_name if log.user else "Аноним"
        details = (log.details or "").replace('"', '""')
        csv_content += f"{log.id},\"{username}\",\"{log.action}\",\"{details}\",{log.created_at.strftime('%Y-%m-%d %H:%M') if log.created_at else ''}\n"
    
    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=logs_{datetime.now().strftime('%Y-%m-%d')}.csv"}
    )
