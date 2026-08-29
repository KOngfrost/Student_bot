# Автономный запуск на VPS

Эта инструкция запускает VK-бота на удаленном Linux-сервере. После завершения SSH-сессии ноутбук можно выключить: Docker продолжит держать bot и PostgreSQL запущенными на VPS.

## 1. Подготовьте сервер

Арендуйте небольшой VPS с Ubuntu 22.04/24.04 или другой поддерживаемой Linux-системой. Рекомендуется 1 CPU, 1 GB RAM и 10 GB SSD.

Подключитесь по SSH:

```bash
ssh user@SERVER_IP
```

Установите Docker официальным способом для выбранного дистрибутива и проверьте:

```bash
docker --version
docker compose version
```

Если Docker требует группу пользователя, выполните и перелогиньтесь:

```bash
sudo usermod -aG docker $USER
```

## 2. Загрузите проект

```bash
git clone REPOSITORY_URL student_bot
cd student_bot
```

Не загружайте `.env` в Git и не вставляйте токен в командную строку.

## 3. Создайте секреты

```bash
nano .env
```

Минимальный набор:

```env
VK_BOT_TOKEN=your_vk_community_token
ADMIN_VK_IDS=123456789
VK_REPORT_ADMIN_ID=123456789
POSTGRES_USER=student_bot
POSTGRES_PASSWORD=long_random_database_password
POSTGRES_DB=student_bot
DB_HOST=db
DB_PORT=5432
REPORT_TIME=09:00
```

Ограничьте права файла:

```bash
chmod 600 .env
```

## 4. Запустите в фоне

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail 100 bot
```

Ожидаемый статус обоих сервисов: `Up`. Проверка базы:

```bash
docker compose exec db pg_isready -U student_bot -d student_bot
```

## 5. Обновление проекта

```bash
cd ~/student_bot
git pull
docker compose up -d --build
docker image prune -f
```

`docker image prune -f` удаляет только неиспользуемые промежуточные образы, но не named volume PostgreSQL.

## 6. Автозапуск после перезагрузки

В Compose задано `restart: unless-stopped`. Включите Docker при старте ОС:

```bash
sudo systemctl enable --now docker
docker compose up -d
```

Проверьте после перезагрузки VPS:

```bash
docker compose ps
```

## 7. Резервная копия PostgreSQL

```bash
mkdir -p ~/student_bot/backups
docker compose exec -T db pg_dump -U student_bot -d student_bot > ~/student_bot/backups/student_bot_$(date +%F).sql
```

Копируйте дампы за пределы VPS. Сам Docker volume не заменяет резервную копию.

## 8. Диагностика

```bash
docker compose ps
docker compose logs --tail 200 bot
docker compose logs --tail 200 db
docker compose restart bot
```

Если бот не отвечает, проверьте Long Poll API, события сообщений и действительность токена в настройках VK-сообщества. Убедитесь, что в логах нет ошибок подключения к PostgreSQL или `VKAPIError`.

## Почему нужен VPS

VK Long Poll - это постоянное соединение. Одноразовая serverless-функция завершится и перестанет получать события. Нужен VPS, облачный worker или другой постоянно работающий сервис. Для текущего проекта самый простой вариант - VPS с Docker Compose.
