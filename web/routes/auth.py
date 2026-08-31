"""
Маршруты аутентификации веб-панели.

Безопасность:
- Пользователи хранятся в таблице web_users, пароли — только в виде
  PBKDF2-хешей (web/security/passwords.py).
- Резервный вход по WEB_ADMIN_USERNAME/WEB_ADMIN_PASSWORD из .env
  (bootstrap-суперадмин, пока web_users не заведены).
- Rate limiting: не более 5 неудачных попыток за 15 минут на IP,
  затем временная блокировка.
- Журналирование входов в таблицу logs + уведомление суперадмина в VK
  при срабатывании блокировки.
- Timing-safe сравнение, поворот CSRF-токена после входа.
"""

import logging
import secrets
import time
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from core.config import settings
from core.database import async_session_maker
from core.models import Log, WebRole, WebUser
from core.ticket_service import send_vk_message
from web.security.csrf import get_csrf_token
from web.security.passwords import verify_password
from web.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()

CREDENTIALS_NOT_SET = (
    "Вход не настроен: создайте пользователя через scripts/create_web_user.py "
    "или задайте WEB_ADMIN_USERNAME и WEB_ADMIN_PASSWORD в .env"
)

# Rate limiting: 5 неудачных попыток за 15 минут на IP
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_WINDOW_SECONDS = 15 * 60

# _LOGIN_ATTEMPTS[ip] = [timestamp неудачных попыток]
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}


def _credentials_configured() -> bool:
    return bool(settings.WEB_ADMIN_USERNAME and settings.WEB_ADMIN_PASSWORD)


def _is_rate_limited(ip: str) -> bool:
    """Превышен ли лимит неудачных попыток входа для IP."""
    now = time.time()
    window_start = now - _LOGIN_WINDOW_SECONDS
    attempts = [t for t in _LOGIN_ATTEMPTS.get(ip, []) if t > window_start]
    _LOGIN_ATTEMPTS[ip] = attempts
    return len(attempts) >= _LOGIN_MAX_ATTEMPTS


def _record_failed_attempt(ip: str) -> None:
    """Зафиксировать неудачную попытку входа."""
    now = time.time()
    window_start = now - _LOGIN_WINDOW_SECONDS
    attempts = [t for t in _LOGIN_ATTEMPTS.get(ip, []) if t > window_start]
    attempts.append(now)
    _LOGIN_ATTEMPTS[ip] = attempts


def _clear_attempts(ip: str) -> None:
    _LOGIN_ATTEMPTS.pop(ip, None)


def _get_client_ip(request: Request) -> str:
    """Получить реальный IP клиента (за reverse-proxy — из X-Forwarded-For)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def _log_action(action: str, details: str) -> None:
    """Записать событие входа в журнал (таблица logs)."""
    try:
        async with async_session_maker() as session:
            session.add(Log(user_id=None, action=action, details=details))
            await session.commit()
    except Exception:
        logger.exception("Не удалось записать событие входа в журнал")


async def _notify_superadmin(details: str) -> None:
    """Уведомить суперадминистратора о подозрительной активности (VK + журнал)."""
    logger.warning("Подозрительная активность: %s", details)
    if settings.VK_REPORT_ADMIN_ID:
        await send_vk_message(
            settings.VK_REPORT_ADMIN_ID,
            f"⚠️ Веб-админка: подозрительная активность\n{details}",
        )


async def _authenticate(username: str, password: str) -> dict | None:
    """Аутентифицировать пользователя: сначала web_users, затем .env-bootstrap."""
    try:
        async with async_session_maker() as session:
            web_user = await session.scalar(
                select(WebUser).where(WebUser.username == username)
            )
            if web_user is not None:
                if not web_user.is_active:
                    return None
                if not verify_password(password, web_user.password_hash):
                    return None
                web_user.last_login_at = datetime.now()
                await session.commit()
                return {
                    "username": web_user.username,
                    "role": web_user.role.value,
                    "web_user_id": web_user.id,
                    "department_id": web_user.department_id,
                }
    except Exception:
        # БД недоступна — пробуем bootstrap-вход из .env
        logger.exception("Не удалось проверить web_users")

    # Bootstrap-вход из .env (до заведения web_users)
    if _credentials_configured():
        username_ok = secrets.compare_digest(
            username.encode("utf-8"), settings.WEB_ADMIN_USERNAME.encode("utf-8")
        )
        password_ok = secrets.compare_digest(
            password.encode("utf-8"), settings.WEB_ADMIN_PASSWORD.encode("utf-8")
        )
        if username_ok and password_ok:
            return {
                "username": username,
                "role": WebRole.SUPERADMIN.value,
                "web_user_id": None,
                "department_id": None,
            }
    return None


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Страница входа."""
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "error": None,
            "csrf_token": get_csrf_token(request),
        },
    )


@router.post("/login")
async def login(request: Request):
    """Обработка входа с rate limiting и журналированием."""
    client_ip = _get_client_ip(request)
    form = await request.form()
    username = str(form.get("username", ""))
    password = str(form.get("password", ""))

    if _is_rate_limited(client_ip):
        details = f"Блокировка IP {client_ip}: превышен лимит попыток входа (username={username!r})"
        await _log_action("web_login_blocked", details)
        await _notify_superadmin(details)
        return templates.TemplateResponse(
            "login.html",
            {
                "request": request,
                "error": "Слишком много попыток входа. Подождите 15 минут.",
            },
            status_code=429,
        )

    user_data = await _authenticate(username, password)

    if user_data is None:
        _record_failed_attempt(client_ip)
        await _log_action(
            "web_login_failed",
            f"Неудачный вход с IP {client_ip} (username={username!r})",
        )
        logger.warning("Неудачная попытка входа с IP %s", client_ip)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный логин или пароль"},
            status_code=401,
        )

    _clear_attempts(client_ip)
    request.session["user"] = user_data
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    await _log_action(
        "web_login_success",
        f"Успешный вход {user_data['username']} (роль {user_data['role']}) с IP {client_ip}",
    )
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout")
async def logout(request: Request):
    """Выход из системы (POST с CSRF-токеном, а не GET)."""
    request.session.clear()
    return RedirectResponse(url="/auth/login", status_code=303)
