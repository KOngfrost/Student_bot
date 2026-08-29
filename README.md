# Student Bot

VK-бот-помощник для студентов на Python, VKBottle, PostgreSQL и SQLAlchemy.
Сейчас реализованы базовое меню, регистрация пользователей, проверка доступа
администратора и отправка Excel-отчетов в VK. Пользовательские сценарии
заявок находятся в разработке.

## Требования

- Python 3.11+
- Docker Desktop / Docker Compose

## Рекомендуемый запуск через Docker Compose

1. Убедитесь, что в корне проекта есть файл `.env`.
2. Запустите сервисы в фоне:

```powershell
docker compose up -d --build
```

3. Проверьте состояние и логи:

```powershell
docker compose ps
docker compose logs -f bot
```

4. Остановите сервисы:

```powershell
docker compose down
```

## Локальный запуск

1. Создайте и активируйте виртуальное окружение:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Установите зависимости:

```powershell
pip install -r requirements.txt
```

3. Создайте файл `.env` со следующим токеном:

```env
VK_BOT_TOKEN=your_vk_token
ADMIN_VK_IDS=123456789,987654321
POSTGRES_USER=student_bot
POSTGRES_PASSWORD=student_bot
POSTGRES_DB=student_bot
DB_HOST=db
DB_PORT=5432
REPORT_TIME=09:00

# SMTP для email-рассылки отчётов (необязательно)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM=your_email@gmail.com
REPORT_EMAILS=admin1@example.com,admin2@example.com
```

4. Запустите приложение:

```powershell
python main.py
```

Для локальной PostgreSQL укажите в `.env` `DB_HOST=127.0.0.1` и реальные
реквизиты базы. Для полного описания автономного запуска откройте
[DEPLOYMENT.md](DEPLOYMENT.md).

## Автономная работа без ноутбука и локального ПК

Бот использует VK Long Poll, поэтому ему нужен постоянно работающий процесс.
Разместите проект на удаленном VPS или облачной виртуальной машине с Docker.
Подойдет небольшой Linux-сервер с 1 CPU, 1 GB RAM и 10 GB диска.

```bash
docker compose up -d --build
```

После выхода из SSH-сессии бот продолжит работать, а `restart: unless-stopped`
перезапустит его после сбоя или перезагрузки VPS. Полностью без сервера запустить
VK Long Poll нельзя; managed-сервис подходит, если поддерживает постоянный
worker-процесс и PostgreSQL.

## Сборка контейнера

```powershell
docker build -t student_bot .
```

## Примечания

- Нужны `VK_BOT_TOKEN` и доступный PostgreSQL.
- `ADMIN_VK_IDS` содержит VK ID администраторов через запятую.
- Администратор получает кнопку Excel-отчета в меню, файл отправляется главному
	администратору прямо в VK. `VK_REPORT_ADMIN_ID` задает его VK ID.
- Схема БД управляется через Alembic-миграции (`alembic/versions/`).
  При старте приложения миграции применяются автоматически.
- Данные пользователей сохраняются между перезапусками в PostgreSQL.
- Каждый день в `REPORT_TIME` Excel-отчет автоматически отправляется главному
	администратору в VK и (при наличии SMTP-настроек) по email.
- Отчёт содержит три листа: «Сводка» (по отделам и % выполнения),
  «Детализация» (все заявки) и «Анонимные обращения».

## Миграции Alembic

Проект использует Alembic для версионирования схемы БД. При старте приложения
миграции применяются автоматически (`alembic upgrade head`).

Применить миграции вручную:

```powershell
alembic upgrade head
```

Создать новую миграцию после изменения моделей:

```powershell
alembic revision --autogenerate -m "описание изменения"
```

Проверить, что схема БД соответствует моделям:

```powershell
alembic check
```

В Docker-окружении команды выполняются внутри контейнера бота:

```powershell
docker compose exec bot alembic upgrade head
```
