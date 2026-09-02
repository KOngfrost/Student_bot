"""
Маршруты базы знаний.

Безопасность:
- CSRF защищён middleware CSRFMiddleware в main.py
- IDOR: админ видит только записи своего отдела (суперадмин — все)
- Санитизация входных данных от XSS
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import logging

from core.database import async_session_maker
from core.models import KnowledgeBase, Department
from web.dependencies import get_admin_scope, require_writer
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
async def knowledge_base_page(request: Request, user=Depends(require_admin)):
    """Страница базы знаний с IDOR-защитой."""
    from web.security.csrf import get_csrf_token

    knowledge_base = []
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
                kb_result = await session.execute(
                    select(KnowledgeBase)
                    .options(selectinload(KnowledgeBase.department))
                    .order_by(KnowledgeBase.id)
                )
            else:
                kb_result = await session.execute(
                    select(KnowledgeBase)
                    .options(selectinload(KnowledgeBase.department))
                    .where(
                        (KnowledgeBase.department_id == dept_id) | (KnowledgeBase.department_id.is_(None))
                    )
                    .order_by(KnowledgeBase.id)
                )
            knowledge_base = kb_result.scalars().all()
    except Exception as e:
        db_error = True
        logger.error("Не удалось загрузить базу знаний: %s", e)

    return templates.TemplateResponse(
        "knowledge_base.html",
        {
            "request": request,
            "user": user,
            "knowledge_base": knowledge_base,
            "departments": departments,
            "db_error": db_error,
            "active": "knowledge",
            "success": request.session.pop("success", None),
            "error": request.session.pop("error", None),
            "csrf_token": get_csrf_token(request),
        }
    )


@router.post("/")
async def add_knowledge_base(request: Request, user=Depends(require_writer)):
    """Добавление записи в базу знаний.

    Безопасность:
    - CSRF: защищён middleware CSRFMiddleware
    - VIEWER не может изменять данные (require_writer)
    - Санитизация входных данных от XSS
    """
    form = await request.form()
    department_id = int(form.get("department_id", 0))
    keywords = sanitize_html(form.get("keywords", ""))
    answer = sanitize_html(form.get("answer", ""))

    try:
        async with async_session_maker() as session:
            is_super, dept_id = await get_admin_scope(session, user)
            if not is_super and dept_id != department_id:
                request.session["error"] = "Нет прав для работы с этим отделом"
                return RedirectResponse(url="/knowledge/", status_code=302)
            kb = KnowledgeBase(
                department_id=department_id,
                keywords=keywords,
                answer=answer,
            )
            session.add(kb)
            await session.commit()
    except Exception as e:
        request.session["error"] = f"Ошибка: {e}"
        return RedirectResponse(url="/knowledge/", status_code=302)

    request.session["success"] = "Запись добавлена в базу знаний"
    return RedirectResponse(url="/knowledge/", status_code=302)


@router.post("/{kb_id}/delete")
async def delete_knowledge_base(request: Request, kb_id: int, user=Depends(require_writer)):
    """Удаление записи из базы знаний (POST с CSRF-токеном) с проверкой прав."""
    try:
        async with async_session_maker() as session:
            kb = await session.get(KnowledgeBase, kb_id)
            if not kb:
                request.session["error"] = "Запись не найдена"
                return RedirectResponse(url="/knowledge/", status_code=302)

            # Проверяем права: админ видит только записи своего отдела
            is_super, dept_id = await get_admin_scope(session, user)

            if not is_super and kb.department_id != dept_id:
                request.session["error"] = "Нет прав для удаления этой записи"
                return RedirectResponse(url="/knowledge/", status_code=302)

            await session.delete(kb)
            await session.commit()
    except Exception as e:
        request.session["error"] = f"Ошибка: {e}"
        return RedirectResponse(url="/knowledge/", status_code=302)

    request.session["success"] = "Запись удалена"
    return RedirectResponse(url="/knowledge/", status_code=302)
