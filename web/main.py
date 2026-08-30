import os
import secrets
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware

from core.database import engine
from core.models import Base
from web.templating import templates  # noqa: F401 (реэкспорт для обратной совместимости)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Student Bot Admin Panel",
    description="Веб-админка для управления ботом студенческого совета",
    version="1.0.0",
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

# Session middleware для авторизации.
# Секрет должен быть стабильным между перезапусками, иначе все сессии
# инвалидируются при каждом деплое.
_session_secret = os.getenv("SESSION_SECRET_KEY")
if not _session_secret:
    _session_secret = secrets.token_urlsafe(64)
    logger.warning(
        "SESSION_SECRET_KEY не задан: используется временный секрет, "
        "сессии будут сбрасываться при перезапуске"
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=_session_secret,
    max_age=3600,
)

# Static
app.mount("/static", StaticFiles(directory="web/static"), name="static")

# Создаём таблицы при старте (только если БД доступна)
@app.on_event("startup")
async def startup():
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        # Игнорируем ошибки подключения к БД при локальном тестировании
        print(f"Warning: Could not connect to database: {e}")


# Глобальный обработчик ошибок
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Обрабатывает все необработанные исключения."""
    logger.exception("Необработанное исключение на %s: %s", request.url.path, exc)
    if request.url.path.startswith("/tickets/"):
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
