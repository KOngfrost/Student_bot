from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from core.database import async_session_maker
from core.models import KnowledgeBase, Department
from web.templating import templates

router = APIRouter()


def require_admin(request: Request) -> dict:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=302, detail="Redirect", headers={"Location": "/auth/login"})
    return user


@router.get("/")
async def knowledge_base_page(request: Request, user=Depends(require_admin)):
    knowledge_base = []
    departments = []
    try:
        async with async_session_maker() as session:
            kb_result = await session.execute(
                select(KnowledgeBase)
                .options(selectinload(KnowledgeBase.department))
                .order_by(KnowledgeBase.id)
            )
            knowledge_base = kb_result.scalars().all()
            
            depts_result = await session.execute(select(Department))
            departments = depts_result.scalars().all()
    except Exception:
        pass
    
    return templates.TemplateResponse(
        "knowledge_base.html",
        {
            "request": request,
            "user": user,
            "knowledge_base": knowledge_base,
            "departments": departments,
            "active": "knowledge",
            "success": request.session.pop("success", None),
            "error": request.session.pop("error", None),
        }
    )


@router.post("/")
async def add_knowledge_base(request: Request, user=Depends(require_admin)):
    form = await request.form()
    department_id = int(form.get("department_id", 0))
    keywords = form.get("keywords", "")
    answer = form.get("answer", "")
    
    try:
        async with async_session_maker() as session:
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


@router.get("/{kb_id}/delete")
async def delete_knowledge_base(request: Request, kb_id: int, user=Depends(require_admin)):
    try:
        async with async_session_maker() as session:
            kb = await session.get(KnowledgeBase, kb_id)
            if kb:
                await session.delete(kb)
                await session.commit()
    except Exception as e:
        request.session["error"] = f"Ошибка: {e}"
        return RedirectResponse(url="/knowledge/", status_code=302)
    
    request.session["success"] = "Запись удалена"
    return RedirectResponse(url="/knowledge/", status_code=302)
