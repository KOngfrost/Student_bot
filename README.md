# 🤖 Student Bot — Бот студенческого совета

Многоканальная система управления обращениями студентов с **VK-ботом** и **веб-админ-панелью**. Система принимает заявки от студентов по направлениям (жилбыт, культмасс, информ, корпоративный, анонимные), маршрутизирует их по отделам, позволяет администраторам обрабатывать заявки и формирует автоматические отчёты.

---

## 📐 Архитектура

```
┌──────────────┐       ┌──────────────────────┐       ┌─────────────────┐
│  VK (клиент) │──────▶│  VK Bot (vk-bot)     │       │  Веб-админка    │
│              │       │  (vkbottle)            │       │  (FastAPI)      │
│              │◀──────│  - Приём обращений     │◀──────│  - Управление   │
│              │       │  - Генерация клавиатур │       │    заявками     │
│              │       │  - Отчёты              │       │  - Журналы      │
└──────────────┘       └──────────┬───────────┘       └─────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  Core (ядро)            │
                    │  - Модели SQLAlchemy     │
                    │  - Database (asyncpg)    │
                    │  - Reporting (Excel)     │
                    │  - Config (.env)         │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  PostgreSQL             │
                    │  (SQLAlchemy ORM)        │
                    └─────────────────────────┘
```

---

## 🚀 Быстрый старт

### 1. Клонирование

```bash
git clone <repo-url>
cd student_bot
```

### 2. Переменные окружения

Создайте файл `.env`:

```env
# VK Bot
VK_TOKEN=your_vk_token
VK_GROUP_ID=your_group_id

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=student_bot
DB_USER=postgres
DB_PASS=postgres

# Web Admin
WEB_ADMIN_USERNAME=admin
WEB_ADMIN_PASSWORD=secure_password
SESSION_SECRET_KEY=your-64-char-secret

# Reporting
REPORT_TIME=23:00
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=bot@example.com
SMTP_PASSWORD=app_password
SMTP_FROM=bot@example.com
REPORT_EMAILS=admin@example.com
VK_REPORT_ADMIN_ID=123456789
```

### 3. Запуск базы данных

```bash
docker-compose up -d
```

### 4. Миграции БД

```bash
python -m alembic upgrade head
```

# Применить миграции:
docker exec student_bot_app python -m alembic upgrade head

# Создать новую миграцию:
docker exec student_bot_app python -m alembic revision --autogenerate -m "comment"

# Откатить миграцию:
docker exec student_bot_app python -m alembic downgrade -1

### 5. Инициализация суперадмина

```bash
python scripts/init_superadmin.py --vk-id 193626953 --name "Иванов Иван"
```

### 6. Запуск приложения

```bash
python main.py
```

---

## 🏗️ Структура проекта

```
student_bot/
├── main.py                     # Точка входа (запуск бота + веб-сервера)
├── core/                       # Ядро системы
│   ├── config.py               # Конфигурация (.env, settings)
│   ├── models.py               # SQLAlchemy модели (User, Ticket, Department, Admin)
│   ├── database.py             # Подключение к PostgreSQL (asyncpg, SQLAlchemy)
│   ├── reporting.py            # Генерация Excel-отчётов + рассылка
│   ├── bot_core.py             # Общая логика бота (обработка заявок)
│   └── vk_compat.py            # VK-совместимость
├── bots/                       # VK-бот
│   └── vk/
│       ├── bot.py              # VK-бот (vkbottle), приём обращений, отчёты
│       └── keyboards.py        # Генерация VK-клавиатур
├── web/                        # Веб-админ-панель
│   ├── main.py                 # FastAPI приложение, middleware безопасности
│   ├── templating.py           # Jinja2 шаблоны
│   ├── routes/                 # Маршруты
│   │   ├── auth.py             # Аутентификация (login/logout, rate limiting)
│   │   ├── admin_panel.py      # Управление администраторами
│   │   ├── tickets.py          # Управление заявками
│   │   ├── knowledge_base.py   # База знаний
│   │   ├── faq.py              # FAQ
│   │   ├── events.py           # События
│   │   ├── logs.py             # Журналы событий
│   │   └── dashboard.py        # Дашборд
│   └── security/               # Безопасность
│       ├── middleware.py       # Security headers, CSV/XSS защита, rate limiting
│       └── csrf.py             # CSRF-защита
├── alembic/                    # Миграции БД (Alembic)
│   ├── env.py
│   └── versions/
│       ├── 3e786255e64d_initial_schema.py
│       └── a1b2c3d4e5f6_add_indexes_and_constraints.py
├── scripts/                    # Вспомогательные скрипты
│   ├── init_superadmin.py      # Инициализация суперадмина
│   └── check_db.py             # Проверка подключения к БД
└── tests/                      # Тесты
    └── test_security.py        # Тесты безопасности (CSRF, XSS, CSV-injection)
```

---

## 🔑 Ключевые функции

### VK-бот (`bots/vk/bot.py`)

| Функция / Команда | Описание |
|---|---|
| `/start` | Регистрация пользователя, приветствие |
| **Жилбыт / Культмасс / Информ / Корпоративный** | Создание заявки по выбранному направлению |
| **Анонимное обращение** | Создание анонимной заявки (без привязки к пользователю) |
| **Мои заявки** | Просмотр статуса активных заявок пользователя |
| **Сформировать отчет** | Генерация и отправка Excel-отчёта администратору |

**Основные функции бота:**
- `create_ticket()` — создание новой заявки (студент + отдел + тема + описание)
- `get_user_active_tickets()` — получение активных заявок пользователя
- `build_daily_report()` — генерация Excel-отчёта (3 листа: сводка, детализация, анонимные)
- `send_report_to_vk()` — отправка отчёта в VK как документ
- `start_report_scheduler()` — планировщик ежедневных отчётов (asyncio)

### Веб-админ-панель (`web/main.py` + `web/routes/`)

| Маршрут | Описание |
|---|---|
| `GET /auth/login` | Страница входа |
| `POST /auth/login` | Вход с rate limiting (5 попыток / 5 мин) |
| `GET /auth/logout` | Выход из системы |
| `GET /` | Дашборд (статистика, графики) |
| `GET /tickets` | Список всех заявок |
| `POST /tickets` | Создание заявки |
| `PUT /tickets/{id}` | Обновление статуса заявки |
| `GET /tickets/{id}` | Детали заявки |
| `GET /admin/admins` | Управление администраторами |
| `POST /admin/admins` | Добавление администратора |
| `GET /knowledge` | База знаний |
| `GET /faq` | FAQ |
| `GET /events` | События |
| `GET /logs` | Журналы событий |

**Основные функции роутеров:**
- `login_page()` / `login()` — аутентификация с CSRF и rate limiting
- `require_auth()` — декоратор проверки авторизации
- `get_current_user()` — получение данных текущего пользователя из сессии
- CRUD-операции для заявок, администраторов, базы знаний, событий

### Ядро (`core/`)

| Модуль | Описание |
|---|---|
| `config.py` | Загрузка настроек из `.env` (питоний settings) |
| `models.py` | SQLAlchemy модели: `User`, `Ticket`, `Department`, `Admin`, `KnowledgeBaseItem`, `FAQ`, `Event`, `LogEntry` |
| `database.py` | `ensure_database_exists()`, `run_migrations()`, `get_session()` |
| `reporting.py` | `build_daily_report()`, `send_report_email()`, `send_report_to_vk()`, `start_report_scheduler()` |

### Безопасность (`web/security/`)

| Компонент | Описание |
|---|---|
| `SecurityHeadersMiddleware` | X-Frame-Options, CSP, X-Content-Type-Options, Permissions-Policy |
| `CSRFMiddleware` | CSRF-токены для всех POST-запросов |
| `sanitize_csv_field()` | Защита от CSV-injection (экранирование `=`, `SHELL|`, `@`) |
| `sanitize_html()` | XSS-санитизация (экранирование `<script>`, `onerror`, `javascript:`) |
| `hash_password()` / `verify_password()` | Безопасное хеширование паролей (timing-safe) |
| `RequestSizeValidator` | Валидация размера запроса (лимит 10MB) |
| `check_rate_limit()` | Rate limiting (защита от брутфорса) |

---

## 📊 Модели данных

### `User` — Пользователь
- `id`, `vk_id`, `full_name`, `dormitory`, `created_at`

### `Ticket` — Заявка
- `id`, `user_id` (FK), `department_id` (FK), `topic`, `description`
- `status` (NEW → IN_PROGRESS → COMPLETED / TRANSFERRED_ADMIN / TRANSFERRED_HOUSEKEEPING / ANONYMOUS)
- `is_anonymous`, `auto_closed`, `response_text`, `created_at`, `updated_at`

### `Department` — Отдел
- `id`, `name`, `created_at`

### `Admin` — Администратор
- `id`, `user_id` (FK), `department_id` (FK), `role` (SUPERADMIN / ADMIN)

### `KnowledgeBaseItem` — Элемент базы знаний
- `id`, `title`, `content`, `category`, `created_at`

### `FAQ` — Частые вопросы
- `id`, `question`, `answer`, `category`, `created_at`

### `Event` — Событие
- `id`, `title`, `description`, `start_date`, `end_date`, `created_at`

### `LogEntry` — Запись журнала
- `id`, `action`, `details`, `user_id`, `created_at`

---

## 🔄 Жизненный цикл заявки

```
Создание (VK-бот)
       │
       ▼
   [NEW] ──────────────────────────────┐
       │                               │
       ▼ (принять в работу)           │
   [IN_PROGRESS] ──────────────────────┤
       │                               │
       ▼ (передать администратору)     │
   [TRANSFERRED_ADMIN] ────────────────┤
       │                               │
       ▼ (передать хозяйственный отдел)│
   [TRANSFERRED_HOUSEKEEPING] ─────────┤
       │                               │
       ▼ (завершить)                   │
   [COMPLETED] ◄───────────────────────┘
       │
       ▼ (автозакрытие через 24ч)
   [COMPLETED_AUTO]
```

---

## 📋 Автоматические отчёты

Система автоматически формирует и рассылает **ежедневные Excel-отчёты**:

1. **Лист «Сводка»** — статистика по отделам (новые, в обработке, выполненные, % выполнения)
2. **Лист «Детализация»** — полный список всех заявок за день
3. **Лист «Анонимные обращения»** — фильтр по анонимным заявкам

**Каналы доставки:**
- **VK** — как документ в личку администратора
- **Email** — как вложение через SMTP

Планировщик работает через `asyncio.create_task()` и запускается при старте бота. Время отчёта настраивается в `REPORT_TIME` (по умолчанию `23:00`).

---

## 🛡️ Меры безопасности

| Угроза | Защита |
|---|---|
| CSRF-атаки | CSRF-токены в сессиях, валидация на всех POST-запросах |
| Брутфорс логина | Rate limiting: 5 попыток за 5 минут на IP |
| Timing-атаки | `secrets.compare_digest()` для сравнения паролей |
| XSS | HTML-экранирование, Content-Security-Policy |
| CSV-injection | Экранирование `=`, `SHELL|`, `@` в полях |
| Clickjacking | `X-Frame-Options: DENY`, `frame-ancestors 'none'` |
| Раскрытие информации | Глобальный обработчик ошибок без деталей, удаление `Server` заголовка |
| Перегруженные запросы | Валидация размера тела (лимит 10MB) |
| Несанкционированный доступ | Session-куки с `HttpOnly`, `Secure`, `SameSite=strict` |

---

## 🧪 Тестирование

```bash
# Запуск тестов безопасности
pytest tests/test_security.py -v
```

Тесты покрывают:
- CSRF-защиту
- Security Headers
- CSV-injection защиту
- XSS-санитизацию
- Хеширование паролей (timing-safe)
- Валидацию размера запроса
- Интеграционные тесты FastAPI-приложения

---

## 📝 Конфигурация

Все настройки хранятся в `.env`:

| Переменная | Описание | По умолчанию |
|---|---|---|
| `VK_TOKEN` | Токен VK бота | — |
| `VK_GROUP_ID` | ID группы VK | — |
| `DB_HOST` | Хост PostgreSQL | `localhost` |
| `DB_PORT` | Порт PostgreSQL | `5432` |
| `DB_NAME` | Имя базы данных | `student_bot` |
| `DB_USER` | Пользователь БД | `postgres` |
| `DB_PASS` | Пароль БД | `postgres` |
| `WEB_ADMIN_USERNAME` | Логин веб-админки | — |
| `WEB_ADMIN_PASSWORD` | Пароль веб-админки | — |
| `SESSION_SECRET_KEY` | Секрет сессий | (случайный при запуске) |
| `REPORT_TIME` | Время отчётов | `23:00` |
| `SMTP_HOST` | SMTP-сервер | — |
| `SMTP_PORT` | SMTP-порт | `587` |
| `SMTP_USER` | SMTP-пользователь | — |
| `SMTP_PASSWORD` | SMTP-пароль | — |
| `SMTP_FROM` | От кого письма | — |
| `REPORT_EMAILS` | Email получателей | — |
| `VK_REPORT_ADMIN_ID` | VK ID получателя отчётов | — |

---

## 📦 Зависимости

Основные библиотеки:
- **vkbottle** — VK Bot API
- **FastAPI + Uvicorn** — Веб-фреймворк
- **SQLAlchemy + asyncpg** — Асинхронная работа с PostgreSQL
- **Alembic** — Миграции БД
- **Jinja2** — Шаблоны веб-интерфейса
- **openpyxl** — Генерация Excel-отчётов
- **pytest** — Тестирование

Полный список в `requirements.txt`.

---

## 🔧 Вспомогательные скрипты

### Инициализация суперадмина
```bash
python scripts/init_superadmin.py --vk-id 193626953 --name "Иванов Иван"
```

### Проверка подключения к БД
```bash
python scripts/check_db.py
```

### Миграции
```bash
python -m alembic upgrade head    # Применить миграции
python -m alembic downgrade base  # Откатить все миграции
python -m alembic revision --autogenerate -m "comment"  # Создать новую миграцию
```

---

## 🚀 Деплой

1. Запустите PostgreSQL (Docker или облако)
2. Настройте `.env` с production-значениями
3. Установите `SESSION_SECRET_KEY` (случайная строка 64+ символов)
4. Примените миграции: `alembic upgrade head`
5. Инициализируйте суперадмина
6. Запустите приложение: `python main.py`

Для продакшена рекомендуется:
- Запускать через `systemd` или Docker Compose
- Размещать за reverse-proxy (Nginx) с HTTPS
- Настроить `SESSION_SECRET_KEY` в переменных окружения хоста
# Применить миграции:
docker exec student_bot_app python -m alembic upgrade head

# Создать новую миграцию:
docker exec student_bot_app python -m alembic revision --autogenerate -m "comment"

# Откатить миграцию:
docker exec student_bot_app python -m alembic downgrade -1