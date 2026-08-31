"""
CSRF-защита для FastAPI-приложения.

Генерирует и проверяет CSRF-токены через сессию.
Токен хранится в сессии и передаётся в скрытом поле формы.
При POST-запросе токен из формы сравнивается с токеном из сессии.
"""

import secrets
from typing import Optional

from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware


CSRF_SESSION_KEY = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"
CSRF_FORM_FIELD = "csrf_token"


class CSRFMiddleware(BaseHTTPMiddleware):
    """Middleware для генерации CSRF-токена и проверки POST-запросов."""

    async def dispatch(self, request: Request, call_next):
        # GET/HEAD/OPTIONS — генерируем токен, если его нет в сессии
        if request.method in ("GET", "HEAD", "OPTIONS"):
            if CSRF_SESSION_KEY not in request.session:
                request.session[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)
            response = await call_next(request)
            return response

        # POST/PUT/DELETE/PATCH — проверяем токен
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            # Пытаемся получить токен из заголовка или формы
            token_from_header = request.headers.get(CSRF_HEADER_NAME)
            token_from_form = None
            token_from_session: Optional[str] = request.session.get(CSRF_SESSION_KEY)

            if not token_from_header and token_from_session:
                # Пытаемся получить форму, только если токен не в заголовке
                try:
                    form = await request.form()
                    token_from_form = form.get(CSRF_FORM_FIELD)
                except Exception:
                    # Если форма не доступна (JSON-запрос и т.п.),
                    # пропускаем проверку — CSRF не требуется для API
                    pass

            if token_from_header and token_from_session:
                if not secrets.compare_digest(token_from_header, token_from_session):
                    raise HTTPException(
                        status_code=403,
                        detail="Недействительный CSRF-токен",
                    )
            elif token_from_form and token_from_session:
                if not secrets.compare_digest(token_from_form, token_from_session):
                    raise HTTPException(
                        status_code=403,
                        detail="Недействительный CSRF-токен",
                    )
            else:
                # Если токен отсутствует — для POST-форм это 403
                # Для JSON-API запросов (без формы) — пропускаем
                if token_from_form is None and token_from_header is None:
                    # Проверяем, является ли запрос формой или JSON
                    content_type = request.headers.get("content-type", "")
                    if "application/json" in content_type:
                        # JSON-запросы без CSRF — пропускаем
                        pass
                    else:
                        # Форма без токена — 403
                        raise HTTPException(
                            status_code=403,
                            detail="Отсутствует CSRF-токен. Обновите страницу и повторите.",
                        )

            response = await call_next(request)
            return response

        # Другие методы — пропускаем
        response = await call_next(request)
        return response


def get_csrf_token(request: Request) -> str:
    """Получить текущий CSRF-токен из сессии."""
    return request.session.get(CSRF_SESSION_KEY, "")


def rotate_csrf_token(request: Request) -> str:
    """
    Повернуть CSRF-токен и вернуть новый.
    Вызывается после чувствительных операций (логин, смена роли).
    """
    new_token = secrets.token_urlsafe(32)
    request.session[CSRF_SESSION_KEY] = new_token
    return new_token


def validate_csrf(request: Request, token: str) -> bool:
    """Валидировать CSRF-токен из формы/заголовка."""
    token_from_session: Optional[str] = request.session.get(CSRF_SESSION_KEY)
    if not token_from_session:
        return False
    return secrets.compare_digest(token, token_from_session)
