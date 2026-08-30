import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()


class Settings:
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


settings = Settings()