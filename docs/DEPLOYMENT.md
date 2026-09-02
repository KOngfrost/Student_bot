# Развёртывание

## Требования

- Ubuntu 22.04/24.04 или совместимый Linux-сервер
- Docker Engine и Docker Compose v2.24+
- VK community token с включённым Long Poll API
- Закрытый SSH-доступ; порт PostgreSQL наружу не открывать

## Запуск

```bash
git clone https://github.com/KOngfrost/Student_bot.git /opt/student_bot
cd /opt/student_bot
cp .env.example .env
chmod 600 .env
```

Заполните `.env`: `POSTGRES_*`, `VK_BOT_TOKEN`, `ADMIN_VK_IDS`, `VK_REPORT_ADMIN_ID`, `SESSION_SECRET_KEY`, `REPORT_TIME` и `APP_TIMEZONE`. Секрет сессии создайте так:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
```

Запуск и проверка:

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail 100 migrate
docker compose logs --tail 100 bot web-admin
curl -s http://127.0.0.1:8000/health
```

Приложение не создаёт схему в production. Изменения БД проходят только через `migrate`/Alembic.

## Доступ к панели

Порт панели привязан к `127.0.0.1:8000`. Для удалённого доступа рекомендуется Tailscale:

```bash
chmod +x scripts/setup_tailscale.sh
./scripts/setup_tailscale.sh
```

Скрипт включает HTTPS и `SESSION_HTTPS_ONLY=true`. Не публикуйте 5432 и 8000 в интернет; на firewall оставьте SSH и доступ Tailscale.

## Резервное копирование

```bash
chmod +x scripts/backup.sh scripts/restore.sh
./scripts/backup.sh
./scripts/restore.sh /var/backups/student_bot/<копия>.sql.gz
```

Храните копии вне сервера и регулярно проверяйте восстановление. Перед restore остановите `bot` и `web-admin`.

## Обновление и откат

```bash
git pull
docker compose up -d --build
docker compose logs migrate
```

Не откатывайте миграции без резервной копии. Для диагностики используйте `docker compose ps` и `docker compose logs --tail 200 <service>`.

## Отказы

`/health` возвращает 503 при недоступной БД. Outbox повторяет доставку VK до лимита попыток; записи блокируются на время обработки, поэтому несколько воркеров не выбирают одну pending-запись одновременно.
