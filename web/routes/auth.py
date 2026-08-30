from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import secrets

from web.templating import templates

router = APIRouter()

# Хранилище админов (в продакшене использовать хэши и БД!)
# Для генерации хэша: pwd_context.hash("your_password")
ADMINS = {
    "admin": "admin123",  # Логин:пароль (измените в продакшене!)
}


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
        {"request": request, "error": None}
    )


@router.post("/login")
async def login(request: Request):
    """Обработка входа. Логин и пароль приходят из HTML-формы."""
    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))

    expected_password = ADMINS.get(username)
    # compare_digest защищает от timing-атак.
    # Сравниваем байты: secrets.compare_digest не поддерживает
    # не-ASCII строки (например, кириллические пароли).
    password_ok = expected_password is not None and secrets.compare_digest(
        password.encode("utf-8"), expected_password.encode("utf-8")
    )
    if password_ok:
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
