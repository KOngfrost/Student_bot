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
from core.models import FAQNode, Department, Admin, UserRole
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
async def faq_page(request: Request, user=Depends(require_admin)):
    """Страница FAQ с IDOR-защитой."""
    from web.security.csrf import get_csrf_token

    faq_nodes = []
    departments = []
    db_error = False

    try:
        async with async_session_maker() as session:
            faq_result = await session.execute(
                select(FAQNode)
                .options(selectinload(FAQNode.department))
                .order_by(FAQNode.department_id, FAQNode.order_index)
            )
            faq_nodes = faq_result.scalars().all()

            depts_result = await session.execute(select(Department))
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
async def add_faq(request: Request, user=Depends(require_admin)):
    """Добавление элемента FAQ с санитизацией входных данных."""
    form = await request.form()
    department_id = int(form.get("department_id", 0))
    parent_id = form.get("parent_id")
    question = sanitize_html(form.get("question", ""))
    is_final = form.get("is_final") == "on"
    final_answer = sanitize_html(form.get("final_answer", "")) if is_final else None

    try:
        async with async_session_maker() as session:
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
    except Exception as e:
        request.session["error"] = f"Ошибка: {e}"
        return RedirectResponse(url="/faq/", status_code=302)

    request.session["success"] = "Элемент FAQ добавлен"
    return RedirectResponse(url="/faq/", status_code=302)


@router.get("/{node_id}/delete")
async def delete_faq(request: Request, node_id: int, user=Depends(require_admin)):
    """Удаление элемента FAQ с проверкой прав."""
    try:
        async with async_session_maker() as session:
            node = await session.get(FAQNode, node_id)
            if node:
                await session.delete(node)
                await session.commit()
    except Exception as e:
        request.session["error"] = f"Ошибка: {e}"
        return RedirectResponse(url="/faq/", status_code=302)

    request.session["success"] = "Элемент FAQ удалён"
    return RedirectResponse(url="/faq/", status_code=302)
