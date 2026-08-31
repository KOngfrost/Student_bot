"""
Модуль безопасности: заголовки, rate limiting, валидация ввода.
"""

import hashlib
import logging
import re
import time
from collections import defaultdict
from typing import Optional

from fastapi import Request, HTTPException, status
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


# === Безопасные заголовки ===

SECURITY_HEADERS = {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
}

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self';"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Добавляет заголовки безопасности к каждому ответу."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        response.headers["Content-Security-Policy"] = CONTENT_SECURITY_POLICY
        # Скрываем заголовок Server
        if "Server" in response.headers:
            del response.headers["Server"]
        if "x-powered-by" in response.headers:
            del response.headers["x-powered-by"]
        return response


# === Rate Limiting ===

class RateLimiter:
    """Простой rate limiter на основе sliding window."""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        window_start = now - self.window_seconds

        # Очищаем старые записи
        self.requests[key] = [
            t for t in self.requests[key] if t > window_start
        ]

        if len(self.requests[key]) >= self.max_requests:
            return False

        self.requests[key].append(now)
        return True


# Глобальные лимитеры
_login_rate_limiter = RateLimiter(max_requests=5, window_seconds=300)  # 5 попыток за 5 минут


def check_rate_limit(key: str, limiter: RateLimiter) -> bool:
    """Проверить, не превышен ли лимит запросов."""
    return limiter.is_allowed(key)


# === CSV Injection защита ===

# Паттерны для обнаружения CSV-инъекций
_CSV_INJECTION_PATTERNS = [
    re.compile(r'^[=+\-@]'),          # Начинается с =, +, -, @
    re.compile(r'\b(CMD\|)', re.IGNORECASE),
    re.compile(r'\b(SHELL\|)', re.IGNORECASE),
    re.compile(r'\b(IMPORT\|)', re.IGNORECASE),
    re.compile(r'\b(PICKLIST\|)', re.IGNORECASE),
    re.compile(r'\b(DATATABLE\|)', re.IGNORECASE),
    re.compile(r'!A\d'),              # Ссылки на ячейки
    re.compile(r'`.*`'),              # Backtick-инъекции
]


def sanitize_csv_field(value: str) -> str:
    """
    Санитизировать поле для CSV-экспорта.
    Убирает символы, которые могут вызвать CSV-injection.
    """
    if not value:
        return ""

    value = str(value)

    # Проверяем паттерны инъекций
    for pattern in _CSV_INJECTION_PATTERNS:
        if pattern.search(value):
            # Экранируем, добавляя табуляцию в начало
            return f"\t{value}"

    return value


def escape_for_csv(value: str) -> str:
    """
    Полная экранировка поля для CSV.
    Заменяет кавычки и оборачивает в кавычки при необходимости.
    """
    if not value:
        return ""

    value = str(value)
    # Экранируем двойные кавычки
    value = value.replace('"', '""')

    # Проверяем, нужно ли оборачивать в кавычки
    if ',' in value or '"' in value or '\n' in value or '\r' in value:
        value = f'"{value}"'

    return value


# === XSS защита для данных в БД ===

# Паттерны для обнаружения XSS
_XSS_PATTERNS = [
    re.compile(r'<script[^>]*>', re.IGNORECASE),
    re.compile(r'javascript:', re.IGNORECASE),
    re.compile(r'on\w+\s*=', re.IGNORECASE),  # onclick=, onerror= и т.д.
    re.compile(r'<iframe[^>]*>', re.IGNORECASE),
    re.compile(r'<object[^>]*>', re.IGNORECASE),
    re.compile(r'<embed[^>]*>', re.IGNORECASE),
    re.compile(r'<form[^>]*>', re.IGNORECASE),
    re.compile(r'<img[^>]*\bonerror', re.IGNORECASE),
    re.compile(r'<svg[^>]*\bonload', re.IGNORECASE),
]


def sanitize_html(value: str) -> str:
    """
    Базовая санитизация HTML для предотвращения XSS.
    Используется для данных, которые НЕ должны содержать HTML-теги.
    """
    if not value:
        return ""

    value = str(value)

    # Проверяем наличие XSS-паттернов
    for pattern in _XSS_PATTERNS:
        if pattern.search(value):
            logger.warning("Обнаружен потенциальный XSS-паттерн: %s", value[:200])

    # HTML-экранирование
    value = value.replace("&", "&amp;")
    value = value.replace("<", "&lt;")
    value = value.replace(">", "&gt;")
    value = value.replace('"', "&quot;")
    value = value.replace("'", "&#x27;")

    return value


# === Валидация размера запроса ===

class RequestSizeValidator:
    """Валидатор размера запроса."""

    def __init__(self, max_body_size: int = 10 * 1024 * 1024):  # 10MB по умолчанию
        self.max_body_size = max_body_size

    def check_content_length(self, request: Request) -> None:
        """Проверить Content-Length заголовок."""
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_body_size:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Размер запроса превышает лимит {self.max_body_size} байт",
                    )
            except ValueError:
                pass

    async def check_form_size(self, request: Request) -> None:
        """Проверить размер multipart-формы."""
        try:
            form = await request.form()
            total_size = 0
            for _, field in form.multi_items():
                if hasattr(field, "file") and field.file:
                    content = await field.file.read()
                    total_size += len(content)
                    field.file.seek(0)  # Восстанавливаем позицию
                elif hasattr(field, "__len__"):
                    total_size += len(str(field))
            if total_size > self.max_body_size:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Размер формы превышает лимит {self.max_body_size} байт",
                )
        except HTTPException:
            raise
        except Exception:
            pass  # Если не удаётся проверить — пропускаем


# === Hash-утилиты ===

def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """
    Хешировать пароль с использованием PBKDF2.
    Возвращает (хеш, salt).
    """
    import os
    import base64

    if salt is None:
        salt = base64.b64encode(os.urandom(16)).decode()

    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    )
    return base64.b64encode(hashed).decode(), salt


def verify_password(password: str, hashed: str, salt: str) -> bool:
    """Проверить пароль против захешированного значения."""
    import base64
    import secrets

    hashed_input = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    )
    input_hash = base64.b64encode(hashed_input).decode()
    return secrets.compare_digest(input_hash, hashed)
