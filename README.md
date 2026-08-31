# 🤖 Student Bot — Бот студенческого совета

Система управления обращениями студентов: **VK-бот** (vkbottle) + **веб-панель
администратора** (FastAPI) + **PostgreSQL** (SQLAlchemy async, Alembic).

Студенты создают заявки по направлениям (Жилбыт, Культмасс, Информ,
Корпоративный, анонимные), администраторы отвечают через веб-панель (ответ
приходит студенту в VK), система формирует ежедневные Excel-отчёты.

---

## 🚀 Быстрый старт

```bash
git clone https://github.com/KOngfrost/Student_bot.git /opt/student_bot
cd student_bot
cp .env.example .env
chmod 600 .env          # заполните переменные (см. .env.example и DEPLOYMENT.md)
docker compose up -d --build
```

Порядок запуска: **PostgreSQL → миграции Alembic (контейнер `migrate`) → бот и
веб-панель**. Проверка: `curl http://127.0.0.1:8000/health` → `{"status":"ok"}`.

Полная инструкция по установке на сервер: [DEPLOYMENT.md](DEPLOYMENT.md).

### Обязательные переменные `.env`

| Переменная | Назначение |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | База данных |
| `VK_BOT_TOKEN` | Токен сообщества VK |
| `ADMIN_VK_IDS` | VK ID админов бота (через запятую) |
| `VK_REPORT_ADMIN_ID` | Получатель отчётов и уведомлений безопасности |
| `SESSION_SECRET_KEY` | Секрет сессий панели (**обязателен**, генерация: `python3 -c 'import secrets; print(secrets.token_urlsafe(64))'`) |
| `WEB_ADMIN_USERNAME` / `WEB_ADMIN_PASSWORD` | Bootstrap-вход в панель (до создания web_users) |
| `APP_TIMEZONE` | Часовой пояс отчётов (по умолчанию `Europe/Moscow`) |
| `REPORT_TIME` | Время ежедневного отчёта `HH:MM` в поясе `APP_TIMEZONE` |
| `ALLOW_DB_CREATE` | В production — `false` (базу создаёт PostgreSQL-контейнер) |

### Создание администраторов

```bash
# VK-суперадмин (админ-команды бота)
docker compose exec bot python scripts/init_superadmin.py --vk-id 123456789 --name "Иванов Иван"

# Пользователь веб-панели (пароль хранится в виде хеша)
docker compose exec bot python scripts/create_web_user.py --username admin --role SUPERADMIN
```

---

## 📐 Архитектура

```
VK (студенты) ◀──▶ VK-бот (long poll) ─┐
                                        ├─▶ PostgreSQL (единая схема, Alembic)
Веб-панель (админы) ◀──▶ FastAPI ───────┘
                              │
                              └─▶ VK API (уведомление студенту об ответе)
```

- **VK-бот**: приём обращений, «Мои заявки» с историей, ежедневные отчёты.
- **Веб-панель**: обработка заявок (ответ/статус/передача), контент, журналы.
- **Общая бизнес-логика**: `core/ticket_service.py` (переходы статусов, история,
  VK-уведомления) используется и ботом, и панелью.

---

## 🏗️ Структура проекта

```
student_bot/
├── main.py                     # Точка входа бота (long poll + планировщик отчётов)
├── core/
│   ├── config.py               # Настройки из .env
│   ├── models.py               # SQLAlchemy-модели (User, Ticket, TicketMessage, WebUser, ReportRun…)
│   ├── database.py             # Движок, сессии, миграции (Alembic)
│   ├── ticket_service.py       # Сервис заявок: история, ответы, статусы, VK-уведомления
│   ├── reporting.py            # Excel-отчёты, планировщик, защита от дублей (report_runs)
│   ├── bot_core.py             # Пользователи, права, журналирование
│   └── heartbeat.py            # Heartbeat бота для healthcheck
├── bots/vk/
│   ├── bot.py                  # Обработчики VK (включая «Мои заявки», «Подробнее #N»)
│   └── keyboards.py            # Клавиатуры VK
├── web/                        # Веб-админ-панель (см. web/README.md)
│   ├── main.py                 # FastAPI, middleware, /health
│   ├── dependencies.py         # Роли и IDOR-скоуп
│   ├── security/               # CSRF, security headers, PBKDF2-хеши
│   └── routes/                 # auth, tickets, dashboard, admins, knowledge, faq, events, logs
├── alembic/                    # Миграции (единственный источник схемы)
├── scripts/
│   ├── init_superadmin.py      # Первый VK-суперадмин
│   ├── create_web_user.py      # Пользователи веб-панели (web_users)
│   ├── healthcheck_bot.py      # Docker healthcheck бота (heartbeat)
│   ├── backup.sh               # Ежедневный pg_dump с ротацией
│   ├── restore.sh              # Восстановление из копии
│   └── check_db.py             # Проверка подключения к БД
├── tests/                      # pytest (config, models, tickets, auth, reports, faq, security)
├── docker-compose.yml          # db + migrate + bot + web-admin (+ tailscale-профиль)
├── docker-compose.tailscale.override.yml
└── .env.example
```

---

## 🔑 Ключевые функции

### VK-бот

| Команда | Описание |
|---|---|
| `/start` | Регистрация, приветствие |
| **Жилбыт / Культмасс / Информ / Корпоративный / Анонимное обращение** | Разделы обращений |
| **Мои заявки** | Список заявок из БД: номер, отдел, тема, дата, статус, ответ администратора |
| **Подробнее #N** | Полная история заявки: вся переписка и системные события |
| **Сформировать отчет** | Excel-отчёт за вчерашний день (только для админов) |
| **Отчет по дате** | Excel-отчёт за одну конкретную дату (формат ДД.ММ.ГГГГ) |
| **Отчет за период** | Excel-отчёт за диапазон дат (формат ДД.ММ.ГГГГ - ДД.ММ.ГГГГ) |

### Веб-панель

| Маршрут | Описание |
|---|---|
| `GET /auth/login`, `POST /auth/login` | Вход (CSRF + rate limit 5/15 мин) |
| `POST /auth/logout` | Выход (POST, не GET) |
| `GET /` | Дашборд (фильтр по отделу) |
| `GET /tickets/` | Заявки (IDOR: админ отдела видит только свой отдел) |
| `GET /tickets/{id}` | Карточка заявки + история переписки (JSON) |
| `POST /tickets/{id}/reply` | Ответ студенту: история + response_text + VK-уведомление + статус |
| `POST /tickets/{id}/status` | Смена статуса с валидацией переходов |
| `POST /tickets/{id}/assign` | Передача в другой отдел (только суперадмин) |
| `GET /health` | Healthcheck (панель + БД) |

### Жизненный цикл заявки

```
NEW → IN_PROGRESS → TRANSFERRED_ADMIN / TRANSFERRED_HOUSEKEEPING → COMPLETED → COMPLETED_AUTO
```

Переходы валидируются в `core/ticket_service.py`; каждое изменение фиксируется
в истории заявки (`ticket_messages`) и журнале (`logs`).

### Ежедневные отчёты

- Время в часовом поясе `APP_TIMEZONE` (по умолчанию Europe/Moscow), даты в БД — UTC.
- Факт отправки сохраняется в `report_runs`: при перезапуске бота отчёт за
  прошедшую дату не отправляется повторно.

---

## 🛡️ Безопасность

| Угроза | Защита |
|---|---|
| Пароли веб-панели | Только PBKDF2-хеши в `web_users` (100k итераций) |
| Брутфорс логина | 5 неудач за 15 минут → блокировка IP + уведомление суперадмина в VK |
| CSRF | Токены в сессии на всех POST-формах |
| IDOR | Админ отдела ограничен своим отделом; VIEWER — только чтение |
| Угон сессии | Cookie `HttpOnly` + `Secure` + `SameSite=strict`, секрет обязателен |
| Clickjacking / XSS | `X-Frame-Options: DENY`, CSP, санитизация ввода |
| Секрет сессии | Без `SESSION_SECRET_KEY` панель не запускается |
| Схема БД | Только Alembic (migrate-контейнер), приложение не создаёт базу в production |
| Панель в интернете | Порт только на `127.0.0.1`; доступ через SSH-туннель или Tailscale |

---

## 🧪 Тестирование и CI

```bash
pip install -r requirements.txt -r requirements-dev.txt
pytest -v          # 89 тестов: config, models, tickets, auth, reports, faq, security
ruff check .       # линтер
mypy core web      # типизация (внедряется постепенно)
```

CI (`.github/workflows/ci.yml`): `ruff → mypy → pytest → docker build`.

---

## 🔧 Вспомогательные скрипты

```bash
python scripts/init_superadmin.py --vk-id 123 --name "Иван Иванов"  # VK-суперадмин
python scripts/create_web_user.py --username admin --role SUPERADMIN  # веб-пользователь
python scripts/healthcheck_bot.py   # проверка heartbeat бота
./scripts/backup.sh                 # резервная копия (cron ежедневно)
./scripts/restore.sh <backup.sql.gz>  # восстановление
python scripts/check_db.py          # проверка подключения к БД
```

Миграции:

```bash
python -m alembic upgrade head      # применить
python -m alembic downgrade -1      # откатить последнюю
python -m alembic revision --autogenerate -m "comment"  # создать новую
```

---

## 📦 Зависимости

vkbottle, FastAPI + Uvicorn, SQLAlchemy + asyncpg, Alembic, Jinja2, openpyxl,
httpx, itsdangerous, tzdata. Полный список — `requirements.txt`
(dev-инструменты — `requirements-dev.txt`).

---

## 📚 Документация

- [DEPLOYMENT.md](DEPLOYMENT.md) — установка на сервер, Tailscale, backup, обновление, откат
- [WEB_ADMIN_GUIDE.md](WEB_ADMIN_GUIDE.md) — руководство администратора панели
- [web/README.md](web/README.md) — устройство веб-панели
- [.env.example](.env.example) — все переменные окружения с комментариями
