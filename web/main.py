"""
Главный модуль FastAPI-приложения.

Включает:
- Безопасные session-куки (https_only, same_site)
- CSRF-защиту (CSRFMiddleware)
- Security Headers (X-Frame-Options, CSP, X-Content-Type-Options и др.)
- Валидацию размера запросов
- Безопасный глобальный обработчик ошибок
"""

import os
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware

from web.templating import templates  # noqa: F401 (реэкспорт для обратной совместимости)
from web.security.csrf import CSRFMiddleware
from web.security.middleware import (
    SecurityHeadersMiddleware,
    RequestSizeValidator,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Student Bot Admin Panel",
    description="Веб-админка для управления ботом студенческого совета",
    version="1.0.0",
)

# === Middleware безопасности (в порядке приоритета) ===

# 1. Security Headers — X-Frame-Options, CSP, X-Content-Type-Options и др.
app.add_middleware(SecurityHeadersMiddleware)

# 2. CSRF защита для всех POST-запросов
app.add_middleware(CSRFMiddleware)

# 3. Session middleware с безопасными настройками
# Секрет ОБЯЗАТЕЛЕН: без него запуск запрещён (иначе сессии сбрасываются
# при каждом перезапуске, что небезопасно и неудобно).
_session_secret = os.getenv("SESSION_SECRET_KEY")
if not _session_secret:
    raise RuntimeError(
        "SESSION_SECRET_KEY не задан. Установите его в .env и перезапустите панель. "
        "Генерация: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    max_age=3600,
    https_only=True,    # Куки только по HTTPS (безопасно при деплое за reverse-proxy)
    same_site="strict", # Защита от CSRF через сторонние сайты
    path="/",
)

# CORS для локальной разработки.
# Внимание: allow_origins=["*"] вместе с allow_credentials=True запрещён
# спецификацией CORS, поэтому явно перечисляем разрешённые источники.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# Валидатор размера запроса (10MB лимит)
_request_size_validator = RequestSizeValidator(max_body_size=10 * 1024 * 1024)


# Middleware для валидации размера запросов
@app.middleware("http")
async def validate_request_size(request: Request, call_next):
    """Проверяет размер запроса до его обработки."""
    await _request_size_validator.check_form_size(request)
    response = await call_next(request)
    return response


# Глобальный обработчик ошибок — без раскрытия деталей
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Обрабатывает все необработанные исключения БЕЗ раскрытия деталей."""
    logger.exception("Необработанное исключение на %s", request.url.path)
    if request.url.path.startswith("/tickets/") and "application/json" in request.headers.get("accept", ""):
        # Для API endpoints возвращаем JSON
        return JSONResponse(
            content={"detail": "Внутренняя ошибка сервера. Проверьте, что БД запущена: docker-compose up -d"},
            status_code=500,
        )
    return HTMLResponse(
        content=(
            "<h1>Ошибка сервера</h1>"
            "<p>Проверьте, что БД запущена: <code>docker-compose up -d</code></p>"
        ),
        status_code=500,
    )


# Импорт роутеров
from web.routes import auth, admin_panel, tickets, knowledge_base, faq, events, logs, dashboard  # noqa: E402

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(admin_panel.router, prefix="/admin/admins", tags=["admin"])
app.include_router(tickets.router, prefix="/tickets", tags=["tickets"])
app.include_router(knowledge_base.router, prefix="/knowledge", tags=["knowledge_base"])
app.include_router(faq.router, prefix="/faq", tags=["faq"])
app.include_router(events.router, prefix="/events", tags=["events"])
app.include_router(logs.router, prefix="/logs", tags=["logs"])
app.include_router(dashboard.router, tags=["dashboard"])


# Healthcheck для мониторинга и docker healthcheck
@app.get("/health")
async def health():
    """Проверка живости панели и доступности БД."""
    from sqlalchemy import text
    from core.database import engine

    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception:
        logger.exception("Healthcheck: БД недоступна")
        return JSONResponse(
            content={"status": "error", "detail": "database unavailable"},
            status_code=503,
        )
