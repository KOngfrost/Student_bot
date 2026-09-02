"""
Маршруты FAQ.

Безопасность:
- CSRF защищён middleware CSRFMiddleware в main.py
- IDOR: админ видит только FAQ своего отдела (суперадмин — все)
- Санитизация входных данных от XSS
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
import logging

from core.database import async_session_maker
from core.models import FAQNode, Department
from web.dependencies import get_admin_scope, require_auth, require_writer
from web.templating import templates
from web.security.middleware import sanitize_html

logger = logging.getLogger(__name__)

router = APIRouter()


require_admin = require_auth


@router.get("/")
async def faq_page(request: Request, user=Depends(require_admin)):
    """Страница FAQ с IDOR-защитой."""
    from web.security.csrf import get_csrf_token

    faq_nodes = []
    departments = []
    db_error = False

    try:
        async with async_session_maker() as session:
            is_super, dept_id = await get_admin_scope(session, user)
            faq_stmt = (
                select(FAQNode)
                .options(selectinload(FAQNode.department))
                .order_by(FAQNode.department_id, FAQNode.order_index)
            )
            if not is_super:
                faq_stmt = faq_stmt.where(FAQNode.department_id == dept_id)
            faq_result = await session.execute(
                faq_stmt
            )
            faq_nodes = faq_result.scalars().all()

            depts_stmt = select(Department)
            if not is_super:
                depts_stmt = depts_stmt.where(Department.id == dept_id)
            depts_result = await session.execute(depts_stmt)
            departments = depts_result.scalars().all()
    except Exception as e:
        db_error = True
        logger.error("Не удалось загрузить FAQ: %s", e)

    return templates.TemplateResponse(
        "faq.html",
        {
            "request": request,
            "user": user,
            "faq_nodes": faq_nodes,
            "departments": departments,
            "db_error": db_error,
            "active": "faq",
            "success": request.session.pop("success", None),
            "error": request.session.pop("error", None),
            "csrf_token": get_csrf_token(request),
        }
    )


@router.post("/")
async def add_faq(request: Request, user=Depends(require_writer)):
    """Добавление элемента FAQ с санитизацией входных данных."""
    form = await request.form()
    department_id = int(form.get("department_id", 0))
    parent_id = form.get("parent_id")
    question = sanitize_html(form.get("question", ""))
    is_final = form.get("is_final") == "on"
    final_answer = sanitize_html(form.get("final_answer", "")) if is_final else None

    try:
        async with async_session_maker() as session:
            is_super, dept_id = await get_admin_scope(session, user)
            if not is_super and dept_id != department_id:
                request.session["error"] = "Нет прав для работы с этим отделом"
                return RedirectResponse(url="/faq/", status_code=302)
            max_order = await session.scalar(
                select(func.coalesce(func.max(FAQNode.order_index), 0))
                .where(FAQNode.department_id == department_id)
            )

            faq_node = FAQNode(
                department_id=department_id,
                parent_id=int(parent_id) if parent_id else None,
                question=question,
                is_final=is_final,
                final_answer=final_answer,
                order_index=max_order + 1,
            )
            session.add(faq_node)
            await session.commit()
    except Exception:
        logger.exception("Не удалось добавить FAQ")
        request.session["error"] = "Не удалось сохранить FAQ. Попробуйте позже."
        return RedirectResponse(url="/faq/", status_code=302)

    request.session["success"] = "Элемент FAQ добавлен"
    return RedirectResponse(url="/faq/", status_code=302)


@router.post("/{node_id}/delete")
async def delete_faq(request: Request, node_id: int, user=Depends(require_writer)):
    """Удаление элемента FAQ (POST с CSRF-токеном) с проверкой прав."""
    try:
        async with async_session_maker() as session:
            node = await session.get(FAQNode, node_id)
            if not node:
                request.session["error"] = "Элемент FAQ не найден"
                return RedirectResponse(url="/faq/", status_code=302)

            # IDOR: админ отдела может удалять только FAQ своего отдела
            is_super, dept_id = await get_admin_scope(session, user)
            if not is_super and dept_id != node.department_id:
                request.session["error"] = "Нет прав для удаления этого элемента FAQ"
                return RedirectResponse(url="/faq/", status_code=302)

            await session.delete(node)
            await session.commit()
    except Exception:
        logger.exception("Не удалось удалить FAQ")
        request.session["error"] = "Не удалось удалить FAQ. Попробуйте позже."
        return RedirectResponse(url="/faq/", status_code=302)

    request.session["success"] = "Элемент FAQ удалён"
    return RedirectResponse(url="/faq/", status_code=302)
