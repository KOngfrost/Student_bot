from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import secrets

from core.config import settings
from web.templating import templates

router = APIRouter()

# Учётные данные веб-админки берутся из .env (WEB_ADMIN_USERNAME /
# WEB_ADMIN_PASSWORD). Никаких дефолтов в коде: пока переменные не заданы,
# вход закрыт с честным сообщением об ошибке.
CREDENTIALS_NOT_SET = "Вход не настроен: задайте WEB_ADMIN_USERNAME и WEB_ADMIN_PASSWORD в .env и перезапустите панель"


def _credentials_configured() -> bool:
    return bool(settings.WEB_ADMIN_USERNAME and settings.WEB_ADMIN_PASSWORD)


async def get_current_user(request: Request) -> dict | None:
    """Проверяет сессию на наличие авторизованного пользователя."""
    user_data = request.session.get("user")
    if user_data:
        return user_data
    return None


def require_auth(request: Request) -> dict:
    """Депенденция для проверки авторизации."""
    user = request.session.get("user")
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=302, detail="Redirect", headers={"Location": "/auth/login"})
    return user


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Страница входа."""
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": None if _credentials_configured() else CREDENTIALS_NOT_SET,
        }
    )


@router.post("/login")
async def login(request: Request):
    """Обработка входа. Логин и пароль приходят из HTML-формы."""
    if not _credentials_configured():
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": CREDENTIALS_NOT_SET},
            status_code=503,
        )

    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))

    # compare_digest защищает от timing-атак.
    # Сравниваем байты: secrets.compare_digest не поддерживает
    # не-ASCII строки (например, кириллические пароли).
    username_ok = secrets.compare_digest(
        username.encode("utf-8"), settings.WEB_ADMIN_USERNAME.encode("utf-8")
    )
    password_ok = secrets.compare_digest(
        password.encode("utf-8"), settings.WEB_ADMIN_PASSWORD.encode("utf-8")
    )
    if username_ok and password_ok:
        user_data = {
            "username": username,
            "role": "superadmin",
        }
        request.session["user"] = user_data
        return RedirectResponse(url="/", status_code=303)

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "error": "Неверный логин или пароль"},
        status_code=401,
    )


@router.get("/logout")
async def logout(request: Request):
    """Выход из системы."""
    request.session.clear()
    return RedirectResponse(url="/auth/login", status_code=302)
