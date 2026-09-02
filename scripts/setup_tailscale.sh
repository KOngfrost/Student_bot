#!/usr/bin/env bash
# Настройка Tailscale доступа к веб-панели Student Bot с автоматическим HTTPS.
#
# Что делает:
#   1. Поднимает стек с профилем tailscale:
#      docker compose -f docker-compose.yml -f docker-compose.tailscale.override.yml \
#        --profile tailscale up -d
#   2. Ждёт, пока tailscale-контейнер получит MagicDNS-имя и IP.
#   3. Включает HTTPS для веб-панели:
#      docker compose ... exec tailscale tailscale serve --bg https / http://localhost:8000
#   4. Устанавливает SESSION_HTTPS_ONLY=true в .env (Secure-cookie работает с HTTPS)
#   5. Перезапускает контейнеры для применения SESSION_HTTPS_ONLY=true
#   6. Печатает URL: https://student-bot-panel.<tailnet>/ — кука Secure работает
#
# Требования:
#   - TAILSCALE_AUTH_KEY в .env (https://login.tailscale.com/admin/settings/keys)
#   - Docker Compose >= 2.24
#
# Использование:
#   ./scripts/setup_tailscale.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
COMPOSE=(docker compose -f "${PROJECT_DIR}/docker-compose.yml" -f "${PROJECT_DIR}/docker-compose.tailscale.override.yml" --profile tailscale)

cd "$PROJECT_DIR"

if [ ! -f .env ]; then
    echo "❌ .env не найден. Скопируйте .env.example в .env и заполните переменные." >&2
    exit 1
fi

if ! grep -q '^TAILSCALE_AUTH_KEY=' .env 2>/dev/null; then
    echo "❌ TAILSCALE_AUTH_KEY не задан в .env. Получите ключ: https://login.tailscale.com/admin/settings/keys" >&2
    exit 1
fi

# Автоматически устанавливаем SESSION_HTTPS_ONLY=true для HTTPS через Tailscale
if grep -q '^SESSION_HTTPS_ONLY=' .env 2>/dev/null; then
    sed -i 's/^SESSION_HTTPS_ONLY=.*/SESSION_HTTPS_ONLY=true/' .env
    echo "✅ SESSION_HTTPS_ONLY установлен в true (Secure-cookie для HTTPS)"
else
    echo "SESSION_HTTPS_ONLY=true" >> .env
    echo "✅ SESSION_HTTPS_ONLY=true добавлен в .env"
fi

echo ""
echo "▶ Запускаем стек с Tailscale..."
"${COMPOSE[@]}" up -d

echo "▶ Ждём готовности tailscale-контейнера..."
for i in $(seq 1 30); do
    if "${COMPOSE[@]}" exec -T tailscale tailscale status >/dev/null 2>&1; then
        break
    fi
    sleep 2
    if [ "$i" -eq 30 ]; then
        echo "❌ Tailscale не стал активным за 60 сек. Смотрите логи: docker compose logs tailscale" >&2
        exit 1
    fi
done

MAGIC_NAME="$("${COMPOSE[@]}" exec -T tailscale tailscale status --json 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); self=d.get('Self'); print(self.get('DNSName','').rstrip('.') if self else '')" 2>/dev/null || true)"
if [ -z "$MAGIC_NAME" ]; then
    MAGIC_NAME="student-bot-panel"
fi

echo "▶ Включаем HTTPS для панели (tailscale serve)..."
"${COMPOSE[@]}" exec -T tailscale tailscale serve --bg https / http://localhost:8000

echo "▶ Перезапускаем контейнеры для применения SESSION_HTTPS_ONLY=true..."
"${COMPOSE[@]}" up -d --force-recreate web-admin

echo ""
echo "✅ Готово! Панель доступна внутри tailnet по адресу:"
echo "   https://${MAGIC_NAME}"
echo ""
echo "📋 Полезные команды:"
echo "   docker compose -f docker-compose.yml -f docker-compose.tailscale.override.yml --profile tailscale up -d"
echo "   docker compose exec student_bot_tailscale tailscale status"
echo "   docker compose exec student_bot_tailscale tailscale serve --help"
echo ""
echo "🔥 Firewall: открыть только 22/tcp. Порты 5432 и 8000 наружу НЕ открывать."