# Веб-админ-панель (FastAPI)

## Запуск

```bash
uvicorn web.main:app --host 0.0.0.0 --port 8000
```

Обязательные переменные окружения (см. `.env.example`):

- `SESSION_SECRET_KEY` — без него приложение **не запустится** (`RuntimeError`);
- `WEB_ADMIN_USERNAME` / `WEB_ADMIN_PASSWORD` — bootstrap-вход, пока в базе
  нет пользователей `web_users` (создаются через `scripts/create_web_user.py`).

## Структура

```
web/
├── main.py              # FastAPI-приложение: middleware, /health, роутеры
├── templating.py        # Jinja2
├── dependencies.py      # Авторизация и роли (SUPERADMIN/DEPARTMENT_ADMIN/VIEWER)
├── security/
│   ├── csrf.py          # CSRF-защита всех POST-форм
│   ├── middleware.py    # Security headers, rate limiter, санитизация, PBKDF2
│   └── passwords.py     # Хеширование паролей web_users
└── routes/
    ├── auth.py          # Вход/выход, rate limit 5/15 мин, журналирование входов
    ├── dashboard.py     # Дашборд с фильтром по отделу
    ├── tickets.py       # Заявки: просмотр, ответ, статус, передача (IDOR-защита)
    ├── admin_panel.py   # VK-администраторы
    ├── knowledge_base.py, faq.py, events.py, logs.py
```

## Модель доступа

- Сессия хранит `{username, role, web_user_id, department_id}`.
- `web/dependencies.py`:
  - `require_auth` — редирект на логин;
  - `require_writer` — 403 для VIEWER;
  - `require_superadmin` — только SUPERADMIN;
  - `get_admin_scope(session, user)` → `(is_super, dept_id)` для IDOR-фильтров.

## Безопасность

- Session cookie: `HttpOnly`, `Secure`, `SameSite=strict`, max_age 1 час.
- CSRF-токен в сессии, проверяется для всех POST/PUT/DELETE/PATCH.
- Rate limiting входа: 5 неудач за 15 минут на IP → блокировка + уведомление
  суперадмина (VK `VK_REPORT_ADMIN_ID` + таблица `logs`).
- Все удаления — только POST с CSRF-токеном и подтверждением.
- CSP, X-Frame-Options: DENY, скрытие заголовка `Server`.
- Лимит размера тела запроса: 10 MB.

## Healthcheck

`GET /health` → `{"status": "ok"}` (выполняет `SELECT 1` в БД; при недоступности
БД — 503). Используется docker healthcheck.
