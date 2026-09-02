# Развёртывание

## Требования

- Ubuntu 22.04/24.04 или совместимый Linux-сервер
- Docker Engine и Docker Compose v2.24+
- VK community token с включённым Long Poll API
- Доступ к панели через Tailscale; порты PostgreSQL и web наружу не открывать

## Запуск

```bash
git clone https://github.com/KOngfrost/Student_bot.git /opt/student_bot
cd /opt/student_bot
cp .env.example .env
chmod 600 .env
```

Заполните `.env`: `POSTGRES_*`, `VK_BOT_TOKEN`, `ADMIN_VK_IDS`, `SESSION_SECRET_KEY`, `REPORT_TIME`, `APP_TIMEZONE` и `TAILSCALE_AUTH_KEY`. Ручной отчет отправляется нажавшему администратору, ежедневный — всем VK-суперадминам из таблицы `admins`. Секрет сессии создайте так:

```bash
python3 -c 'import secrets; print(secrets.token_urlsafe(64))'
```

Запуск и проверка:

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail 100 migrate
docker compose logs --tail 100 bot web-admin
curl -s http://localhost:8000/health
```

Приложение не создаёт схему в production. Изменения БД проходят только через `migrate`/Alembic.

## Доступ к панели

Панель доступна только через Tailscale по адресу
`https://имя-вашей-машины.имя-вашей-сети.ts.net/` в tailnet `имя-вашей-сети.ts.net`.

На Windows PowerShell:

```powershell
Set-ExecutionPolicy -Scope Process RemoteSigned
.\scripts\setup_tailscale.ps1
```

На Linux:

```bash
chmod +x scripts/setup_tailscale.sh
./scripts/setup_tailscale.sh
```

Оба скрипта поднимают профиль, регистрируют узел с именем `student-bot-panel`, ждут
подключения и включают `tailscale serve` для HTTPS.

Ошибка `register request` означает, что контейнер не смог зарегистрироваться в
control plane. Проверьте интернет/DNS внутри Docker и срок действия ключа:

```bash
docker compose logs --tail 200 tailscale
docker compose exec tailscale tailscale status
docker compose exec tailscale tailscale netcheck
```

Если ключ просрочен или отозван, создайте новый auth key в Tailscale Admin
Console, замените `TAILSCALE_AUTH_KEY` в `.env`, затем пересоздайте профиль:

```bash
docker compose -f docker-compose.yml -f docker-compose.tailscale.override.yml --profile tailscale down
docker compose -f docker-compose.yml -f docker-compose.tailscale.override.yml --profile tailscale up -d
```

После регистрации проверьте публикацию:

```bash
docker compose exec tailscale tailscale serve status
curl -vk https://имя-вашей-машины.имя-вашей-сети.ts.net/health
```

URL работает только с устройства, подключенного к той же tailnet.

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
