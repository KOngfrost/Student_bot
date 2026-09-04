# OSS Bot

OSS Bot - сервис приёма и обработки обращений студентов. Обращения приходят через
VK-сообщения, хранятся в PostgreSQL, а администраторы работают с ними в веб-панели
`oss-web-panel` (FastAPI). Ответы панели доставляются студентам через надёжный
outbox-воркер.

Веб-панель доступна только внутри вашей Tailscale-сети (`oss-web-panel.<tailnet>.ts.net`).
Наружу (в интернет) не публикуется ни один порт.

## Состав

| Компонент | Что делает |
|---|---|
| `bot` | VK Long Poll сервис: приём сообщений, создание обращений, админ-команды |
| `web-admin` | Веб-панель на FastAPI (статистика, заявки, FAQ, база знаний, события, логи) |
| `db` | PostgreSQL 16, изолирован внутри docker-сети (порт 5432 наружу не публикуется) |
| `tailscale` | VPN-узел: обеспечивает доступ к панели только из вашего tailnet |
| `migrate` | Одноразовый контейнер Alembic-миграций (выполняется до `bot` и `web-admin`) |

## Требования

- Linux-сервер (Ubuntu 22.04/24.04 или совместимый) с Docker Engine и Docker Compose v2.24+
- Аккаунт Tailscale и Auth key (https://login.tailscale.com/admin/settings/keys)
- Токен сообщества VK с включённым Long Poll API

## Быстрый запуск (Docker)

1. Клонируйте проект и подготовьте конфигурацию:

```bash
git clone https://github.com/KOngfrost/Student_bot.git /opt/oss_bot
cd /opt/oss_bot
cp .env.example .env
chmod 600 .env            # ограничьте права на файл с секретами
```

2. Заполните `.env`:

- `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` - доступы к БД
  (пользователь и пароль НЕ должны быть дефолтными; пароль - не короче 12 символов).
- `VK_BOT_TOKEN` - токен сообщества VK.
- `ADMIN_VK_IDS` - VK ID администраторов через запятую.
- `SESSION_SECRET_KEY` - сгенерируйте случайное значение:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
```

- `TAILSCALE_AUTH_KEY` - ключ из Tailscale Admin Console.

3. Запустите стек (Tailscale поднимается вместе со всеми сервисами):

```bash
docker compose up -d --build
docker compose ps
curl -s http://localhost:8000/health   # ожидается {"status":"ok"} (с самого сервера)
```

4. Включите HTTPS-доступ к панели через Tailscale:

```bash
./scripts/setup_tailscale.sh
```

После этого панель доступна по адресу `https://oss-web-panel.<tailnet>.ts.net/`.

## Доступ к панели

Панель открывается только на устройствах, подключённых к тому же tailnet:

```
https://oss-web-panel.<tailnet>.ts.net/
```

Вход - по учётным данным веб-панели. На пустой базе работает bootstrap-вход из
`.env` (`WEB_ADMIN_USERNAME`/`WEB_ADMIN_PASSWORD`); он отключается после создания
первого пользователя в `web_users`.

## Создание администраторов

```bash
# VK-суперадмин (получает ежедневные отчёты)
docker compose exec bot python scripts/init_superadmin.py --vk-id 123456789 --name "Имя Фамилия"

# Пользователь веб-панели
docker compose exec bot python scripts/create_web_user.py --username admin --role SUPERADMIN
docker compose exec bot python scripts/create_web_user.py --username zhilbyt --role DEPARTMENT_ADMIN --department "Жилбыт"
```

Роли и ограничения описаны в [docs/WEB_ADMIN_GUIDE.md](docs/WEB_ADMIN_GUIDE.md).

## Резервное копирование и восстановление

```bash
chmod +x scripts/backup.sh scripts/restore.sh
./scripts/backup.sh                                   # ежедневная копия + ротация
./scripts/restore.sh /var/backups/oss_bot/oss_bot_2026-09-01.sql.gz
```

Для production настройте удалённую выгрузку `BACKUP_REMOTE` (rclone) и расписание
cron. Подробнее - в [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Проверки (разработка)

```bash
python check_syntax.py
ruff check .
mypy core web
pytest -v
```

## Структура проекта

- `core/` - конфигурация, модели, БД, бизнес-логика заявок и outbox.
- `bots/vk/` - VK-обработчики и клавиатуры.
- `web/` - FastAPI-панель, маршруты, безопасность, шаблоны и стили.
- `alembic/` - миграции схемы БД.
- `scripts/` - администрирование, healthcheck, backup и restore.
- `tests/` - unit- и интеграционные проверки.

## Документация

- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) - установка на пустой сервер, Tailscale, масштабирование, откат.
- [docs/WEB_ADMIN_GUIDE.md](docs/WEB_ADMIN_GUIDE.md) - ежедневная работа в панели.
- [docs/ADMIN_AND_DATABASE_GUIDE.md](docs/ADMIN_AND_DATABASE_GUIDE.md) - таблицы, роли, администраторы.
- [web/README.md](web/README.md) - устройство web-модуля и security-контракт.
- [TECHNICAL_SPEC.md](TECHNICAL_SPEC.md) - историческое техническое задание MVP.

## Производительность

Проект рассчитан на нагрузку более 2500 пользователей. Ключевые настройки:

- Несколько uvicorn-воркеров веб-панели (`WEB_WORKERS`, по умолчанию 4).
- Общий HTTP-клиент VK с keep-alive пулом соединений.
- Outbox-очередь доставки настраивается через `OUTBOX_BATCH_SIZE` и
  `OUTBOX_INTERVAL_SECONDS`.

Подробнее о планировании ёмкости - в разделе "Масштабирование" файла
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).