import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # === Окружение ===
    # Значения: development | production (плюс test/testing для конфигов).
    # В production: запрещены дефолтные креды БД, пустой SESSION_SECRET_KEY и т.п.
    APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
    dev_environments = {"", "development", "dev", "test", "testing", "local"}

    @property
    def IS_PRODUCTION(self) -> bool:
        return self.APP_ENV not in self.dev_environments

    # Database
    DB_USER = os.getenv("POSTGRES_USER", os.getenv("DB_USER", "student_bot"))
    DB_PASS = os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASS", "student_bot"))
    DB_NAME = os.getenv("POSTGRES_DB", os.getenv("DB_NAME", "student_bot"))
    DB_HOST = os.getenv("DB_HOST", "db")
    DB_PORT = os.getenv("DB_PORT", "5432")
    database_url = (
        f"postgresql+asyncpg://{quote_plus(DB_USER)}:{quote_plus(DB_PASS)}"
        f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    )

    # VK
    VK_BOT_TOKEN = os.getenv("VK_BOT_TOKEN")
    ADMIN_VK_IDS = {
        int(value.strip())
        for value in os.getenv("ADMIN_VK_IDS", "").split(",")
        if value.strip().isdigit()
    }
    VK_REPORT_ADMIN_ID = next(
        (
            int(value.strip())
            for value in os.getenv("VK_REPORT_ADMIN_ID", "0").split(",")
            if value.strip().isdigit()
        ),
        0,
    )

    REPORT_TIME = os.getenv("REPORT_TIME", "09:00")

    # Часовой пояс для отчётов и отображения времени пользователям.
    # Даты в БД хранятся в UTC, отчётные границы считаются в этом поясе.
    APP_TIMEZONE = os.getenv("APP_TIMEZONE", "Europe/Moscow")

    # Dev-режим: разрешить приложению самому создавать базу
    # (CREATE DATABASE). В production должно быть false — базу создаёт
    # PostgreSQL-контейнер через POSTGRES_DB, схема применяется через Alembic.
    ALLOW_DB_CREATE = os.getenv("ALLOW_DB_CREATE", "false").lower() in ("1", "true", "yes")

    # Секрет сессий веб-панели (обязателен: без него панель не запускается)
    SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "")

    # === Web admin panel ===
    # https_only для session-cookie:
    #   false (по умолчанию) — доступ по http://localhost или http://tailscale-IP
    #     (SSH-туннель / Tailscale без HTTPS): кука работает по HTTP.
    #   true — панель за Nginx/Caddy с TLS или через Tailscale HTTPS
    #     (tailscale serve): кука помечается Secure и шлётся только по HTTPS.
    SESSION_HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "false").lower() in ("1", "true", "yes")

    # Доверенные reverse-proxy (IP через запятую), от которых разрешено
    # принимать настоящий IP клиента из заголовка X-Forwarded-For.
    # Пусто — заголовок игнорируется (используется прямой IP соединения).
    TRUSTED_PROXIES = {
        ip.strip() for ip in os.getenv("TRUSTED_PROXIES", "").split(",") if ip.strip()
    }

    # Веб-админка: учётные данные входа (без дефолтов —
    # вход невозможен, пока они не заданы в .env)
    WEB_ADMIN_USERNAME = os.getenv("WEB_ADMIN_USERNAME", "")
    WEB_ADMIN_PASSWORD = os.getenv("WEB_ADMIN_PASSWORD", "")

    # SMTP (email-рассылка отчётов)
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM = os.getenv("SMTP_FROM", os.getenv("SMTP_USER", ""))
    REPORT_EMAILS = [
        email.strip()
        for email in os.getenv("REPORT_EMAILS", "").split(",")
        if email.strip()
    ]

    def ensure_production_config(self) -> None:
        """Жёсткие проверки конфигурации для production (запуск прерывается)."""
        if not self.IS_PRODUCTION:
            return
        if self.DB_PASS == "student_bot":
            raise RuntimeError(
                "APP_ENV=production, но POSTGRES_PASSWORD не задан явно "
                "(дефолт 'student_bot' запрещён в production). Укажите пароль в .env."
            )
        if self.DB_USER == "student_bot":
            raise RuntimeError(
                "APP_ENV=production, но POSTGRES_USER не задан явно "
                "(дефолт 'student_bot' запрещён в production)."
            )
        if not self.SESSION_SECRET_KEY or len(self.SESSION_SECRET_KEY) < 32:
            raise RuntimeError(
                "APP_ENV=production, но SESSION_SECRET_KEY не задан или короче 32 символов."
            )


settings = Settings()