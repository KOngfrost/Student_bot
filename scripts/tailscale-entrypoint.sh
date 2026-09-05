#!/bin/sh
set -e

# Запускаем tailscaled в фоне (с учётом TS_USERSPACE из окружения)
if [ "$TS_USERSPACE" = "true" ]; then
    tailscaled --tun=userspace-networking &
else
    tailscaled &
fi
TAILSCALED_PID=$!

# Ждём подключения к control plane
echo "Ожидаем подключения Tailscale..."
for i in $(seq 1 30); do
    if tailscale status >/dev/null 2>&1; then
        echo "Tailscale подключён!"
        break
    fi
    sleep 2
    if [ "$i" -eq 30 ]; then
        echo "ОШИБКА: Tailscale не подключился за 60 секунд" >&2
        kill $TAILSCALED_PID
        exit 1
    fi
done

# Запускаем serve для веб-панели
echo "Включаем HTTPS для панели (tailscale serve)..."
tailscale serve --bg http://localhost:8000

# Ждём завершения работы
wait $TAILSCALED_PID
