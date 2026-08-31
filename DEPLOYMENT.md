# Развёртывание Student Bot (production)

Пошаговая установка на чистый VPS (Ubuntu 22.04/24.04) и эксплуатация.

---

## 1. Требования

- VPS: 1 vCPU / 1–2 GB RAM, 10 GB SSD
- Docker Engine + Docker Compose plugin (v2.24+)
- Токен сообщества VK (Long Poll API включён)
- Доступ по SSH

## 2. Установка Docker

```bash
curl -fsSL https://get.docker.com | sh
docker compose version   # должно быть >= 2.24 (нужно для Tailscale-override)
```

## 3. Клонирование и .env

```bash
git clone https://github.com/KOngfrost/Student_bot.git /opt/student_bot
cd /opt/student_bot
cp .env.example .env
chmod 600 .env
```

Заполните `.env` (обязательность указана в комментарии к каждой переменной):

| Переменная | Назначение |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | База данных |
| `VK_BOT_TOKEN` | Токен сообщества VK |
| `ADMIN_VK_IDS` | VK ID админов бота (через запятую) |
| `VK_REPORT_ADMIN_ID` | Получатель отчётов и уведомлений безопасности |
| `REPORT_TIME` | Время ежедневного отчёта `HH:MM` (в поясе `APP_TIMEZONE`) |
| `APP_TIMEZONE` | Часовой пояс, по умолчанию `Europe/Moscow` |
| `ALLOW_DB_CREATE` | В production — `false` |
| `SESSION_SECRET_KEY` | Секрет сессий веб-панели (**обязателен**, панель не запустится без него) |
| `WEB_ADMIN_USERNAME` / `WEB_ADMIN_PASSWORD` | Bootstrap-вход в панель (до создания web_users) |
| `TAILSCALE_AUTH_KEY` | Только для Tailscale-профиля |

Сгенерируйте секрет сессии:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
```

## 4. Первый запуск

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail 100 bot
```

Порядок запуска контролируется Compose: **PostgreSQL (healthcheck) → миграции Alembic (одноразовый контейнер `migrate`) → бот и веб-панель**. Схема БД изменяется только через Alembic; приложение не создаёт базу (`ALLOW_DB_CREATE=false`).

Проверка здоровья:

```bash
curl -s http://127.0.0.1:8000/health   # {"status":"ok"}
```

## 5. Создание администраторов

**VK-суперадмин** (админ-команды бота):

```bash
docker compose exec bot python scripts/init_superadmin.py --vk-id 123456789 --name "Иванов Иван"
```

**Пользователи веб-панели** (таблица `web_users`, пароль хранится только в виде хеша):

```bash
docker compose exec bot python scripts/create_web_user.py --username admin --role SUPERADMIN
# пароль спросит скрыто

docker compose exec bot python scripts/create_web_user.py \
    --username zhilbyt --role DEPARTMENT_ADMIN --department "Жилбыт"
```

Роли:

| Роль | Права |
|---|---|
| `SUPERADMIN` | Все отделы, передача заявок, управление админами |
| `DEPARTMENT_ADMIN` | Заявки и контент только своего отдела |
| `VIEWER` | Просмотр всего, без изменений |

Пока `web_users` пуст, вход возможен по `WEB_ADMIN_USERNAME`/`WEB_ADMIN_PASSWORD` из `.env` (роль SUPERADMIN). После заведения пользователей в базе bootstrap-вход можно отключить, очистив эти переменные в `.env`.

## 6. Доступ к панели: Tailscale (рекомендуется)

Панель **не публикуется в интернет**: порт привязан к `127.0.0.1:8000`. Варианты доступа:

**Вариант А — SSH-туннель** (без дополнительной настройки):

```bash
ssh -L 8000:127.0.0.1:8000 user@server
# затем открыть http://localhost:8000
```

**Вариант Б — Tailscale** (доступ из приватной сети, без публикации портов):

1. Auth key: https://login.tailscale.com/admin/settings/keys
2. Впишите `TAILSCALE_AUTH_KEY=...` в `.env`
3. Запустите:

```bash
docker compose -f docker-compose.yml -f docker-compose.tailscale.override.yml \
    --profile tailscale up -d
```

Панель доступна внутри tailnet по адресу `http://student-bot-panel:8000`. Порт в интернет при этом не публикуется вообще.

**Firewall сервера:** открыть только `22/tcp`. Порты 5432 (PostgreSQL) и 8000 (панель) наружу не открывать.

## 7. Резервное копирование

```bash
chmod +x scripts/backup.sh scripts/restore.sh
./scripts/backup.sh
```

По умолчанию: `/var/backups/student_bot`, хранение 7 дневных + 4 недельных + 3 месячных копий.

Cron (ежедневно в 03:00):

```bash
crontab -e
# 0 3 * * * /opt/student_bot/scripts/backup.sh >> /var/log/student_bot_backup.log 2>&1
```

**Обязательно** выгружайте копии за пределы VPS (S3, Backblaze B2, rclone) и **раз в месяц проверяйте восстановление**:

```bash
./scripts/restore.sh /var/backups/student_bot/student_bot_2026-08-31.sql.gz
```

## 8. Мониторинг

- `restart: unless-stopped` — автоперезапуск контейнеров.
- Healthcheck веб-панели: `GET /health` (проверяет и доступность БД).
- Healthcheck бота: heartbeat-файл (`scripts/healthcheck_bot.py`), бот обновляет его при обработке событий и раз в минуту.
- Журнал действий: таблица `logs` (входы, ответы, смены статусов).
- Подозрительная активность: 5 неудачных входов за 15 минут → временная блокировка IP + уведомление на `VK_REPORT_ADMIN_ID`.

## 9. Обновление

```bash
cd /opt/student_bot
git pull
docker compose up -d --build
docker compose logs migrate   # убедиться, что миграции прошли
docker image prune -f
```

## 10. Смена секретов

1. Сгенерируйте новый `SESSION_SECRET_KEY`, впишите в `.env`.
2. `docker compose up -d` — все сессии инвалидируются (это ожидаемо).
3. Пароль web_user: `docker compose exec bot python scripts/create_web_user.py --username admin --role SUPERADMIN` (перезапишет пароль).

## 11. Аварийный откат

```bash
# Откатить последнюю миграцию
docker compose run --rm migrate alembic downgrade -1

# Восстановить базу из копии
docker compose stop bot web-admin
./scripts/restore.sh /var/backups/student_bot/student_bot_2026-08-31.sql.gz
docker compose start bot web-admin

# Откат кода
git checkout <предыдущий-тег-или-коммит>
docker compose up -d --build
```

## 12. Диагностика

```bash
docker compose ps
docker compose logs --tail 200 bot
docker compose logs --tail 200 web-admin
docker compose logs --tail 200 migrate
docker compose restart bot
```

Если бот не отвечает, проверьте Long Poll API, события сообщений и действительность токена в настройках VK-сообщества. Убедитесь, что в логах нет ошибок подключения к PostgreSQL или `VKAPIError`.
