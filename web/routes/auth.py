"""
Маршруты аутентификации.

Безопасность:
- Rate limiting на /auth/login (5 попыток за 5 минут)
- Timing-safe сравнение через secrets.compare_digest
- Сессия очищается при logout
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
import secrets
import time
import logging

from core.config import settings
from web.templating import templates
from web.security.middleware import check_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter()

# Учётные данные веб-админки берутся из .env (WEB_ADMIN_USERNAME /
# WEB_ADMIN_PASSWORD). Никаких дефолтов в коде: пока переменные не заданы,
# вход закрыт с честным сообщением об ошибке.
CREDENTIALS_NOT_SET = "Вход не настроен: задайте WEB_ADMIN_USERNAME и WEB_ADMIN_PASSWORD в .env и перезапустите панель"

# Rate limiting: 5 попыток за 5 минут на IP
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 300  # 5 минут


def _credentials_configured() -> bool:
    return bool(settings.WEB_ADMIN_USERNAME and settings.WEB_ADMIN_PASSWORD)


def _is_rate_limited(ip: str) -> bool:
    """Проверить, не превышен ли лимит попыток входа для данного IP."""
    now = time.time()
    window_start = now - _LOGIN_WINDOW_SECONDS

    # Очищаем старые записи
    if ip in _LOGIN_ATTEMPTS:
        _LOGIN_ATTEMPTS[ip] = [
            t for t in _LOGIN_ATTEMPTS[ip] if t > window_start
        ]
    else:
        _LOGIN_ATTEMPTS[ip] = []

    if len(_LOGIN_ATTEMPTS[ip]) >= _LOGIN_MAX_ATTEMPTS:
        return True

    return False


def _record_login_attempt(ip: str) -> None:
    """Зафиксировать попытку входа для IP."""
    now = time.time()
    window_start = now - _LOGIN_WINDOW_SECONDS
    if ip not in _LOGIN_ATTEMPTS:
        _LOGIN_ATTEMPTS[ip] = []
    _LOGIN_ATTEMPTS[ip] = [t for t in _LOGIN_ATTEMPTS[ip] if t > window_start]
    _LOGIN_ATTEMPTS[ip].append(now)


def _get_client_ip(request: Request) -> str:
    """Получить реальный IP клиента."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


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
    from web.security.csrf import get_csrf_token
    csrf_token = get_csrf_token(request)
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": None if _credentials_configured() else CREDENTIALS_NOT_SET,
            "csrf_token": csrf_token,
        }
    )


@router.post("/login")
async def login(request: Request):
    """Обработка входа. Логин и пароль приходят из HTML-формы.

    Безопасность:
    - Rate limiting: 5 попыток за 5 минут на IP
    - Timing-safe сравнение через secrets.compare_digest
    - После успешного входа — поворот CSRF-токена
    """
    if not _credentials_configured():
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": CREDENTIALS_NOT_SET},
            status_code=503,
        )

    client_ip = _get_client_ip(request)

    # Проверка rate limiting
    if _is_rate_limited(client_ip):
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Слишком много попыток входа. Подождите 5 минут.",
            },
            status_code=429,
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

    # Фиксируем попытку (успешную или нет)
    _record_login_attempt(client_ip)

    if username_ok and password_ok:
        user_data = {
            "username": username,
            "role": "superadmin",
        }
        request.session["user"] = user_data
        # Поворот CSRF-токна после успешного входа
        request.session["csrf_token"] = secrets.token_urlsafe(32)
        return RedirectResponse(url="/", status_code=303)

    logger.warning("Неудачная попытка входа с IP %s", client_ip)
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
