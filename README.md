# Student Bot

Student Bot принимает обращения студентов через VK, хранит переписку в PostgreSQL и даёт администраторам веб-панель на FastAPI. Ответы панели доставляются через надёжный outbox-воркер.

## Быстрый запуск

1. Создайте `.env` на основе `.env.example`.
2. Укажите `VK_BOT_TOKEN`, параметры PostgreSQL и случайный `SESSION_SECRET_KEY`.
3. Запустите:

```bash
docker compose up -d --build
docker compose ps
curl -s http://localhost:8000/health
```

Ожидаемый ответ healthcheck: `{"status":"ok"}`. Миграции запускаются одноразовым сервисом `migrate` до бота и панели.

В production веб-панель используется только через Tailscale по адресу
`https://имя-вашей-машины.имя-вашей-сети.ts.net/` (tailnet: `имя-вашей-сети.ts.net/`).

Для локального запуска без Docker:

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m alembic upgrade head
uvicorn web.main:app --reload
python main.py
```

## Администраторы

```bash
docker compose exec bot python scripts/create_web_user.py --username admin --role SUPERADMIN
docker compose exec bot python scripts/create_web_user.py --username zhilbyt --role DEPARTMENT_ADMIN --department "Жилбыт"
```

Роли и ограничения описаны в [docs/WEB_ADMIN_GUIDE.md](docs/WEB_ADMIN_GUIDE.md). Bootstrap-вход из `.env` отключается после появления активного пользователя в `web_users`.

## Структура

- `core/` — конфигурация, модели, БД, бизнес-логика заявок и outbox.
- `bots/vk/` — VK-обработчики и клавиатуры.
- `web/` — FastAPI-панель, маршруты, безопасность, шаблоны и стили.
- `alembic/` — миграции схемы БД.
- `scripts/` — операции администрирования, healthcheck, backup и restore.
- `tests/` — unit- и интеграционные проверки.
- `Status/` — отчёты о состоянии проекта.

## Проверки

```bash
python check_syntax.py
ruff check .
mypy core web
pytest -v
```

## Эксплуатация

- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) — Docker, Tailscale, backup, обновление и диагностика.
- [docs/WEB_ADMIN_GUIDE.md](docs/WEB_ADMIN_GUIDE.md) — ежедневная работа в панели.
- [docs/ADMIN_AND_DATABASE_GUIDE.md](docs/ADMIN_AND_DATABASE_GUIDE.md) — таблицы, роли и управление администраторами.
- [web/README.md](web/README.md) — устройство web-модуля и security-контракт.
- [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) — техническое задание, документ не изменялся.
